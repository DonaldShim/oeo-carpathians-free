from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os, json, asyncio
# OEO_PUBLIC_S3_ANON_V1
# Earth Search COGs are public. Prevent GDAL/rasterio from probing EC2 metadata.
os.environ.setdefault("AWS_NO_SIGN_REQUEST","YES")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED","TRUE")
os.environ.setdefault("AWS_REGION","us-west-2")
os.environ.setdefault("AWS_DEFAULT_REGION","us-west-2")
import httpx
from rio_tiler.io import STACReader
from rio_tiler.colormap import cmap
from rasterio.features import shapes
from rasterio.warp import transform_geom
from rasterio.transform import from_bounds
from pyproj import Geod

ROOT = Path(__file__).parent
STATIC = ROOT / 'static'
CFG = json.loads((ROOT / 'CARPATHIANS_CONFIG.json').read_text(encoding='utf-8'))
EARTH_SEARCH = 'https://earth-search.aws.element84.com/v1'
_EVENT_CACHE = {}

app = FastAPI(title='OEO Карпаты · Полесье 4.2 Free', version='4.2.0-free')
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
async def root():
    return FileResponse(STATIC / 'index.html')

@app.get('/health')
async def health():
    return {
        'monitor':'ok', 'version':'4.2.0-free', 'profile':'render-free',
        'region':'Українські Карпати + Полісся', 'stac':True,
        'sentinel1':True, 'sentinel2':True, 'nisar':True,
        'firms_configured': bool(os.getenv('FIRMS_MAP_KEY')),
        'gfw_mode':'external-evidence','event_engine':'sentinel2-pixel-polygons-v42'
    }

@app.get('/api/config')
async def config():
    return CFG

def _bbox(s: str):
    vals=[float(x) for x in s.split(',')]
    if len(vals)!=4: raise ValueError('bbox must be minLon,minLat,maxLon,maxLat')
    return vals

def _interval(days:int):
    end=datetime.now(timezone.utc)
    start=end-timedelta(days=days)
    return f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}"

async def _stac_search(collection:str,bbox:list,days:int,limit:int,cloud_max=None):
    body={'collections':[collection],'bbox':bbox,'datetime':_interval(days),'limit':limit,'sortby':[{'field':'properties.datetime','direction':'desc'}]}
    if cloud_max is not None:
        body['query']={'eo:cloud_cover':{'lte':cloud_max}}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r=await c.post(f'{EARTH_SEARCH}/search',json=body)
        r.raise_for_status()
        data=r.json()
    out=[]
    for f in data.get('features',[]):
        p=f.get('properties',{})
        assets=f.get('assets',{})
        out.append({
            'id':f.get('id'),'datetime':p.get('datetime') or p.get('start_datetime'),
            'collection':f.get('collection'),'cloud_cover':p.get('eo:cloud_cover'),
            'platform':p.get('platform'),'constellation':p.get('constellation'),
            'bbox':f.get('bbox'),'geometry':f.get('geometry'),
            'thumbnail':(assets.get('thumbnail') or {}).get('href'),
            'visual':(assets.get('visual') or {}).get('href'),
            'vv':(assets.get('vv') or {}).get('href'),
            'vh':(assets.get('vh') or {}).get('href'),
            'asset_keys':sorted(list(assets.keys())),
            'source':'Earth Search / Element 84'
        })
    return out

@app.get('/api/v3/sentinel1/search')
async def sentinel1(bbox:str,days:int=30,max_results:int=12):
    b=_bbox(bbox)
    items=await _stac_search('sentinel-1-grd',b,days,max_results)
    return {'ok':True,'provider':'Earth Search','mission':'Sentinel-1','results':items,'count':len(items)}

@app.get('/api/v3/sentinel2/search')
async def sentinel2(bbox:str,days:int=30,max_results:int=12,cloud_max:int=40):
    b=_bbox(bbox)
    items=await _stac_search('sentinel-2-l2a',b,days,max_results,cloud_max)
    return {'ok':True,'provider':'Earth Search','mission':'Sentinel-2','results':items,'count':len(items)}


# OEO_RASTER_TILES_V32
def _stac_item_url(collection: str, item_id: str):
    return f"{EARTH_SEARCH}/collections/{collection}/items/{item_id}"

S2_MODE_SPEC = {
    "RGB": (["visual"], None, None),
    "NDVI": (["nir", "red"], "(b1-b2)/(b1+b2)", (-1.0, 1.0)),
    "NDWI": (["green", "nir"], "(b1-b2)/(b1+b2)", (-1.0, 1.0)),
    "MNDWI": (["green", "swir16"], "(b1-b2)/(b1+b2)", (-1.0, 1.0)),
    "NDMI": (["nir", "swir16"], "(b1-b2)/(b1+b2)", (-1.0, 1.0)),
    "NBR": (["nir", "swir22"], "(b1-b2)/(b1+b2)", (-1.0, 1.0)),
}

def _s2_tile_sync(item_id: str, mode: str, z: int, x: int, y: int):
    mode = mode.upper()
    if mode not in S2_MODE_SPEC:
        raise ValueError(f"unsupported mode: {mode}")
    assets, expr, rng = S2_MODE_SPEC[mode]
    with STACReader(_stac_item_url("sentinel-2-l2a", item_id)) as src:
        if mode == "RGB":
            img = src.tile(x, y, z, assets=[{"name":"visual","indexes":[1,2,3]}], tilesize=256)
            return img.render(img_format="PNG")
        img = src.tile(x, y, z, assets=assets, expression=expr, tilesize=256)
        img.rescale(in_range=(rng,))
        return img.render(img_format="PNG", colormap=cmap.get("viridis"))

def _s1_tile_sync(item_id: str, pol: str, z: int, x: int, y: int):
    pol = pol.lower()
    if pol not in {"vv","vh","hh","hv"}:
        raise ValueError("unsupported polarization")
    with STACReader(_stac_item_url("sentinel-1-grd", item_id)) as src:
        img = src.tile(x, y, z, assets=[pol], tilesize=256)
        return img.render(img_format="PNG")

@app.get('/api/v3/sentinel2/tile/{item_id}/{mode}/{z}/{x}/{y}.png')
async def sentinel2_tile(item_id: str, mode: str, z: int, x: int, y: int):
    try:
        content = await asyncio.to_thread(_s2_tile_sync, item_id, mode, z, x, y)
        return Response(content=content, media_type="image/png", headers={"Cache-Control":"public, max-age=86400"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sentinel-2 tile error: {str(e)[:220]}")

@app.get('/api/v3/sentinel1/tile/{item_id}/{pol}/{z}/{x}/{y}.png')
async def sentinel1_tile(item_id: str, pol: str, z: int, x: int, y: int):
    try:
        content = await asyncio.to_thread(_s1_tile_sync, item_id, pol, z, x, y)
        return Response(content=content, media_type="image/png", headers={"Cache-Control":"public, max-age=86400"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sentinel-1 tile error: {str(e)[:220]}")

@app.get('/api/v3/nisar/search')
async def nisar(bbox:str,days:int=60,max_results:int=12):
    b=_bbox(bbox)
    try:
        import asf_search as asf
        wkt=f"POLYGON(({b[0]} {b[1]},{b[2]} {b[1]},{b[2]} {b[3]},{b[0]} {b[3]},{b[0]} {b[1]}))"
        end=datetime.now(timezone.utc)
        start=end-timedelta(days=days)
        maturity=getattr(getattr(asf.constants,'MATURITIES',None),'PROVISIONAL','PROVISIONAL')
        results=await asyncio.to_thread(asf.search, dataset='NISAR', processingLevel='GCOV', dataMaturity=maturity, intersectsWith=wkt, start=start, end=end, maxResults=max_results)
        out=[]
        for x in results:
            d=x.geojson() if hasattr(x,'geojson') else {}
            p=d.get('properties',{})
            out.append({'id':p.get('fileID') or p.get('sceneName') or p.get('granuleName'), 'datetime':p.get('startTime'), 'platform':'NISAR', 'processingLevel':p.get('processingLevel'), 'dataMaturity':p.get('dataMaturity') or 'PROVISIONAL', 'geometry':d.get('geometry'), 'source':'NASA ASF'})
        return {'ok':True,'provider':'NASA ASF','mission':'NISAR','results':out,'count':len(out)}
    except Exception as e:
        return {'ok':False,'provider':'NASA ASF','mission':'NISAR','results':[],'count':0,'reason':str(e)[:300]}

@app.get('/api/v3/firms')
async def firms(bbox:str,days:int=5):
    key=os.getenv('FIRMS_MAP_KEY','').strip()
    if not key:
        return {'ok':True,'configured':False,'features':[],'count':0,'reason':'FIRMS_MAP_KEY not configured'}
    b=_bbox(bbox); days=max(1,min(int(days),10))
    area=','.join(str(x) for x in b)
    url=f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{area}/{days}'
    async with httpx.AsyncClient(timeout=30) as c:
        r=await c.get(url); r.raise_for_status(); text=r.text
    rows=[]
    import csv, io
    for row in csv.DictReader(io.StringIO(text)):
        try:
            rows.append({'lat':float(row['latitude']),'lon':float(row['longitude']),'date':row.get('acq_date'),'time':row.get('acq_time'),'confidence':row.get('confidence'),'frp':row.get('frp')})
        except Exception: pass
    return {'ok':True,'configured':True,'features':rows,'count':len(rows)}

@app.get('/api/v3/providers')
async def providers():
    return {
      'ok':True,
      'providers':[
        {'name':'Earth Search','missions':['Sentinel-1','Sentinel-2'],'mode':'live','key_required':False},
        {'name':'NASA ASF','missions':['NISAR'],'mode':'live metadata','key_required':False},
        {'name':'NASA FIRMS','missions':['VIIRS'],'mode':'live when key configured','key_required':True},
        {'name':'Global Forest Watch','missions':['integrated forest alerts'],'mode':'external evidence','key_required':False}
      ]
    }

@app.get('/api/v3/activity/scan')
async def activity_scan(bbox:str,days:int=30):
    b=_bbox(bbox)
    s1_task=_stac_search('sentinel-1-grd',b,days,12)
    s2_task=_stac_search('sentinel-2-l2a',b,days,12,40)
    s1,s2=await asyncio.gather(s1_task,s2_task)
    nisar_data=await nisar(bbox, max(days,60), 12)
    firms_data=await firms(bbox,min(days,10))
    signals=(1 if s1 else 0)+(1 if s2 else 0)+(1 if nisar_data.get('count') else 0)+(1 if firms_data.get('count') else 0)
    return {
      'ok':True,'status':'NO_CONFIRMED_EVENT','evidence_readiness':{'level':'HIGH' if signals>=3 else 'MEDIUM' if signals>=2 else 'LOW','signals':signals,'of':4},
      'summary':{'sentinel1':len(s1),'sentinel2':len(s2),'nisar':nisar_data.get('count',0),'firms':firms_data.get('count',0)},
      'latest':{'sentinel1':s1[:5],'sentinel2':s2[:5],'nisar':nisar_data.get('results',[])[:5],'firms':firms_data.get('features',[])[:10]},
      'interpretation':'Свежие данные найдены. Сам факт появления новых сцен не считается подтверждённым природным или антропогенным событием.'
    }


# OEO_EVENT_CANDIDATES_V42\n_EVENT_CACHE = {}
def _dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z","+00:00"))
    except Exception:
        return None

def _lonlat_tile(lon: float, lat: float, z: int):
    import math
    n=2**z
    x=int((lon+180.0)/360.0*n)
    lat=max(min(lat,85.05112878),-85.05112878)
    y=int((1.0-math.asinh(math.tan(math.radians(lat)))/math.pi)/2.0*n)
    return x,y

def _tile_bounds(x: int, y: int, z: int):
    import math
    n=2**z
    west=x/n*360.0-180.0
    east=(x+1)/n*360.0-180.0
    north=math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n))))
    south=math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+1)/n))))
    return [west,south,east,north]

def _candidate_tiles_for_bbox(bbox, z=12, max_cells=12):
    minlon,minlat,maxlon,maxlat=bbox
    xa,ya=_lonlat_tile(minlon,maxlat,z)
    xb,yb=_lonlat_tile(maxlon,minlat,z)
    xs=list(range(min(xa,xb),max(xa,xb)+1))
    ys=list(range(min(ya,yb),max(ya,yb)+1))
    cells=[(x,y) for y in ys for x in xs]
    if len(cells)<=max_cells:
        return cells
    # Uniform spatial sample over the full AOI, not only the centre.
    import math
    nx=max(1,min(len(xs),int(round(math.sqrt(max_cells*max(1,len(xs))/max(1,len(ys)))))))
    ny=max(1,min(len(ys),max_cells//nx))
    while nx*ny<max_cells and nx<len(xs):
        nx+=1
    while nx*ny<max_cells and ny<len(ys):
        ny+=1
    def picks(vals,n):
        if n>=len(vals):
            return vals
        if n<=1:
            return [vals[len(vals)//2]]
        return [vals[round(i*(len(vals)-1)/(n-1))] for i in range(n)]
    sx=picks(xs,nx); sy=picks(ys,ny)
    out=[(x,y) for y in sy for x in sx]
    return out[:max_cells]

def _index_image(item_id: str, mode: str, z: int, x: int, y: int):
    mode=mode.upper()
    assets,expr,_=S2_MODE_SPEC[mode]
    with STACReader(_stac_item_url("sentinel-2-l2a",item_id)) as src:
        return src.tile(x,y,z,assets=assets,expression=expr,tilesize=256)

def _scl_image(item_id: str, z: int, x: int, y: int):
    with STACReader(_stac_item_url("sentinel-2-l2a",item_id)) as src:
        return src.tile(x,y,z,assets=["scl"],tilesize=256)

_GEOD = Geod(ellps="WGS84")

def _geodesic_area_ha(geom: dict):
    def ring_area(ring):
        if len(ring)<4:
            return 0.0
        lons=[p[0] for p in ring]; lats=[p[1] for p in ring]
        area,_=_GEOD.polygon_area_perimeter(lons,lats)
        return abs(area)
    if geom.get("type")=="Polygon":
        rings=geom.get("coordinates") or []
        if not rings:
            return 0.0
        area=ring_area(rings[0])-sum(ring_area(r) for r in rings[1:])
        return max(0.0,area)/10000.0
    if geom.get("type")=="MultiPolygon":
        total=0.0
        for poly in geom.get("coordinates") or []:
            if poly:
                total+=ring_area(poly[0])-sum(ring_area(r) for r in poly[1:])
        return max(0.0,total)/10000.0
    return 0.0

def _wm_tile_transform(x: int, y: int, z: int, width: int, height: int):
    # Exact slippy-map tile extent in EPSG:3857.
    origin=20037508.342789244
    span=(2.0*origin)/(2**z)
    minx=-origin+x*span
    maxx=minx+span
    maxy=origin-y*span
    miny=maxy-span
    return from_bounds(minx,miny,maxx,maxy,width,height)

def _geom_bbox(geom: dict):
    pts=[]
    def walk(v):
        if isinstance(v,(list,tuple)):
            if len(v)>=2 and isinstance(v[0],(int,float)) and isinstance(v[1],(int,float)):
                pts.append((float(v[0]),float(v[1])))
            else:
                for q in v:
                    walk(q)
    walk(geom.get("coordinates"))
    if not pts:
        return None
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return [min(xs),min(ys),max(xs),max(ys)]

def _scenario_pixel_mask(scenario: str, delta, valid):
    import numpy as np
    if scenario=="forest":
        return valid & (delta < -0.12), "NBR", "Снижение NBR: возможное повреждение/вырубка лесного покрова", 0.35
    if scenario=="fire":
        return valid & (delta < -0.14), "NBR", "Снижение NBR: кандидат следа пожара/повреждения", 0.35
    if scenario=="flood":
        return valid & (delta > 0.12), "NDWI", "Рост NDWI: кандидат расширения воды/переувлажнения", 0.40
    return valid & (np.abs(delta) > 0.12), "NDMI", "Изменение NDMI: кандидат структурного изменения склона/влажности", 0.25

def _cell_change_sync(before_id: str, after_id: str, mode: str, scenario: str, z: int, x: int, y: int):
    import numpy as np
    a=_index_image(before_id,mode,z,x,y)
    b=_index_image(after_id,mode,z,x,y)
    av=np.asarray(a.data[0],dtype="float32")
    bv=np.asarray(b.data[0],dtype="float32")
    am=np.asarray(a.mask)>0
    bm=np.asarray(b.mask)>0
    valid=am & bm & np.isfinite(av) & np.isfinite(bv)
    if valid.sum()<800:
        return None
    delta=np.full(av.shape,np.nan,dtype="float32")
    delta[valid]=bv[valid]-av[valid]
    change_mask,metric,label,min_area_ha=_scenario_pixel_mask(scenario,delta,valid)
    changed=int(change_mask.sum())
    if changed<8:
        return {"stats":{"valid_fraction":float(valid.mean()),"changed_fraction":0.0,"cloud_masked":True},"polygons":[]}
    # Refine only potential-change cells with local Sentinel-2 Scene Classification.
    # Exclude no-data, saturated, cloud shadow, medium/high cloud, cirrus and snow/ice.
    try:
        sa=_scl_image(before_id,z,x,y)
        sb=_scl_image(after_id,z,x,y)
        ca=np.asarray(sa.data[0])
        cb=np.asarray(sb.data[0])
        bad=np.isin(ca,[0,1,3,8,9,10,11]) | np.isin(cb,[0,1,3,8,9,10,11])
        valid=valid & (~bad)
        delta=np.full(av.shape,np.nan,dtype="float32")
        delta[valid]=bv[valid]-av[valid]
        change_mask,metric,label,min_area_ha=_scenario_pixel_mask(scenario,delta,valid)
        changed=int(change_mask.sum())
        if changed<8:
            return {"stats":{"valid_fraction":float(valid.mean()),"changed_fraction":0.0,"cloud_masked":True},"polygons":[]}
    except Exception:
        # Do not fabricate a cloud-free claim if SCL is unavailable.
        return {"stats":{"valid_fraction":float(valid.mean()),"changed_fraction":0.0,"cloud_masked":False,"scl_error":True},"polygons":[]}
    changed_vals=delta[change_mask]
    stats={
        "median_delta":float(np.median(delta[valid])),
        "mean_delta":float(np.mean(delta[valid])),
        "mean_changed_delta":float(np.mean(changed_vals)),
        "median_changed_delta":float(np.median(changed_vals)),
        "changed_fraction":float(changed/valid.sum()),
        "valid_fraction":float(valid.mean()),
        "changed_pixels":changed,
        "cloud_masked":True,
    }
    polys=[]
    px_transform=_wm_tile_transform(x,y,z,change_mask.shape[1],change_mask.shape[0])
    for geom,val in shapes(change_mask.astype("uint8"),mask=change_mask,transform=px_transform):
        if int(val)!=1:
            continue
        try:
            wgs=transform_geom("EPSG:3857","EPSG:4326",geom,precision=6)
            area_ha=_geodesic_area_ha(wgs)
            if area_ha<min_area_ha:
                continue
            polys.append({"geometry":wgs,"bbox":_geom_bbox(wgs),"area_ha":float(area_ha)})
        except Exception:
            continue
    polys.sort(key=lambda p:p["area_ha"],reverse=True)
    return {"stats":stats,"polygons":polys[:8],"metric":metric,"label":label}

def _signal_index(scenario: str, stats: dict, area_ha: float):
    d=abs(float(stats.get("mean_changed_delta",0.0)))
    frac=float(stats.get("changed_fraction",0.0))
    magnitude=min(1.0,max(0.0,(d-0.08)/0.22))
    density=min(1.0,frac/0.25)
    area=min(1.0,max(0.0,area_ha)/8.0)
    return int(round(min(100,max(0,28+42*magnitude+20*density+10*area))))

def _mode_for_scenario(scenario: str):
    return {"forest":"NBR","fire":"NBR","flood":"NDWI","slope":"NDMI"}.get(scenario,"NBR")

async def _pick_compare_scenes(bbox, days):
    items=await _stac_search("sentinel-2-l2a",bbox,max(days,75),18,45)
    if len(items)<2:
        return None,None,items
    after=items[0]
    ad=_dt(after.get("datetime"))
    before=None
    if ad:
        for q in items[1:]:
            qd=_dt(q.get("datetime"))
            if qd and (ad-qd).days>=10:
                before=q; break
    if before is None:
        before=items[min(len(items)-1,5)]
    return before,after,items

@app.get('/api/v3/events/candidates')
async def event_candidates(bbox: str, days: int=30, scenario: str="forest"):
    b=_bbox(bbox)
    scenario=scenario if scenario in {"forest","fire","flood","slope"} else "forest"
    _now=__import__("time").time()
    _key=(tuple(round(v,5) for v in b),int(days),scenario)
    _cached=_EVENT_CACHE.get(_key)
    if _cached and _now-_cached[0] < 600:
        return dict(_cached[1], cache_hit=True)
    before,after,items=await _pick_compare_scenes(b,days)
    events=[]
    diagnostics={"scene_count":len(items),"mode":_mode_for_scenario(scenario)}
    if before and after and before.get("id")!=after.get("id"):
        mode=_mode_for_scenario(scenario)
        cells=_candidate_tiles_for_bbox(b,12,12)
        async def one(xy):
            x,y=xy
            try:
                st=await asyncio.to_thread(_cell_change_sync,before["id"],after["id"],mode,scenario,12,x,y)
                return x,y,st
            except Exception as e:
                return x,y,{"error":str(e)[:160]}
        rows=await asyncio.gather(*(one(c) for c in cells))
        polygon_count=0
        for x,y,st in rows:
            if not st or "error" in st:
                continue
            stats=st.get("stats") or {}
            for j,p in enumerate(st.get("polygons") or []):
                polygon_count+=1
                area_ha=float(p.get("area_ha") or 0.0)
                idx=_signal_index(scenario,stats,area_ha)
                events.append({
                    "id":f"cand-{scenario}-12-{x}-{y}-{j}",
                    "class":"candidate",
                    "scenario":scenario,
                    "title":st.get("label") or "Кандидат изменения",
                    "signal_index":idx,
                    "signal_label":"индекс сигнала, не вероятность",
                    "status":"CANDIDATE_REQUIRES_CONFIRMATION",
                    "source":"Sentinel-2 cloud-masked pixel temporal index",
                    "mode":st.get("metric") or mode,
                    "before":{"id":before["id"],"datetime":before.get("datetime")},
                    "after":{"id":after["id"],"datetime":after.get("datetime")},
                    "bbox":p.get("bbox"),
                    "geometry":p.get("geometry"),
                    "area_ha":round(area_ha,2),
                    "delta_index":round(float(stats.get("mean_changed_delta",0.0)),4),
                    "changed_fraction":round(float(stats.get("changed_fraction",0.0)),4),
                    "analysis_geometry":"cloud_masked_pixel_polygon",
                    "metrics":{k:round(v,4) if isinstance(v,float) else v for k,v in stats.items()}
                })
        events.sort(key=lambda e:(e.get("signal_index",0),e.get("area_ha",0)),reverse=True)
        events=events[:24]
        diagnostics.update({
            "before":before.get("datetime"),"after":after.get("datetime"),
            "tested_cells":len(cells),"candidate_polygons":len(events),
            "raw_polygons":polygon_count,"geometry":"cloud_masked_pixel_polygon","tile_zoom":12,"tile_pixels":256,"sampling":"uniform_aoi"
        })
    else:
        diagnostics["reason"]="not enough comparable Sentinel-2 scenes"

    # Direct thermal alerts if FIRMS is configured.
    f=await firms(bbox,min(days,10))
    for i,p in enumerate(f.get("features") or []):
        lon=float(p["lon"]); lat=float(p["lat"])
        events.append({
            "id":f"firms-{i}-{p.get('date','')}-{p.get('time','')}",
            "class":"direct",
            "scenario":"fire",
            "title":"FIRMS / VIIRS: термоаномалия",
            "signal_index":100,
            "signal_label":"прямой тепловой алерт",
            "status":"DIRECT_THERMAL_ALERT",
            "source":"NASA FIRMS VIIRS",
            "geometry":{"type":"Point","coordinates":[lon,lat]},
            "point":[lon,lat],
            "date":p.get("date"),"time":p.get("time"),"frp":p.get("frp"),"firms_confidence":p.get("confidence")
        })
    _result={
        "ok":True,
        "scenario":scenario,
        "events":events,
        "count":len(events),
        "direct_count":sum(1 for e in events if e["class"]=="direct"),
        "candidate_count":sum(1 for e in events if e["class"]=="candidate"),
        "firms_configured":bool(os.getenv("FIRMS_MAP_KEY")),
        "gfw_mode":"external-evidence",
        "diagnostics":diagnostics,
        "warning":"Candidate polygons are pixel-level screening signals, not confirmed incidents. signal_index is an internal signal score, not a calibrated probability. Direct FIRMS points are thermal alerts.",
        "cache_hit":False
    }
    _EVENT_CACHE[_key]=(_now,_result)
    if len(_EVENT_CACHE)>48:
        for k in list(_EVENT_CACHE)[:16]:
            _EVENT_CACHE.pop(k,None)
    return _result

# OEO_RENDER_BOOT_SELFTEST_V2
def _tile_xyz(lon: float, lat: float, z: int):
    import math
    n=2**z
    x=int((lon+180.0)/360.0*n)
    lat_rad=math.radians(lat)
    y=int((1.0-math.asinh(math.tan(lat_rad))/math.pi)/2.0*n)
    return x,y,z

async def _boot_selftest():
    await asyncio.sleep(2)
    bbox="24.35,48.02,24.90,48.35"
    result={"bbox":bbox}
    s1_items=[]; s2_items=[]
    try:
        s1=await sentinel1(bbox=bbox,days=30,max_results=4)
        s1_items=s1.get("results") or []
        result["sentinel1"]={"ok":s1.get("ok"),"count":s1.get("count")}
    except Exception as e:
        result["sentinel1"]={"ok":False,"error":str(e)[:180]}
    try:
        s2=await sentinel2(bbox=bbox,days=30,max_results=4,cloud_max=60)
        s2_items=s2.get("results") or []
        result["sentinel2"]={"ok":s2.get("ok"),"count":s2.get("count")}
    except Exception as e:
        result["sentinel2"]={"ok":False,"error":str(e)[:180]}
    try:
        nr=await nisar(bbox=bbox,days=90,max_results=4)
        result["nisar"]={"ok":nr.get("ok"),"count":nr.get("count"),"reason":nr.get("reason")}
    except Exception as e:
        result["nisar"]={"ok":False,"error":str(e)[:180]}
    try:
        fr=await firms(bbox=bbox,days=5)
        result["firms"]={"ok":fr.get("ok"),"configured":fr.get("configured"),"count":fr.get("count")}
    except Exception as e:
        result["firms"]={"ok":False,"error":str(e)[:180]}
    try:
        ev=await event_candidates(bbox=bbox,days=30,scenario="forest")
        candidates=[e for e in (ev.get("events") or []) if e.get("class")=="candidate"]
        top=candidates[0] if candidates else {}
        result["event_engine"]={
            "ok":ev.get("ok"),
            "count":ev.get("count"),
            "direct_count":ev.get("direct_count"),
            "candidate_count":ev.get("candidate_count"),
            "tested_cells":(ev.get("diagnostics") or {}).get("tested_cells"),
            "geometry":(ev.get("diagnostics") or {}).get("geometry"),
            "tile_pixels":(ev.get("diagnostics") or {}).get("tile_pixels"),
            "before":(ev.get("diagnostics") or {}).get("before"),
            "after":(ev.get("diagnostics") or {}).get("after"),
            "top_signal_index":top.get("signal_index"),
            "top_area_ha":top.get("area_ha"),
            "top_delta_index":top.get("delta_index"),
            "top_geometry_type":(top.get("geometry") or {}).get("type"),
            "legacy_confidence_present":"confidence" in top if top else False
        }
    except Exception as e:
        result["event_engine"]={"ok":False,"error":str(e)[:220]}

    try:
        html=(STATIC/"index.html").read_text(encoding="utf-8")
        js=(STATIC/"app.js").read_text(encoding="utf-8")
        result["ui_contract"]={
            "v42_brand":"Полесье 4.2" in html,
            "footprints_default_off":'id="footprints"' in html and 'id="footprints" checked' not in html,
            "finding_filters":'id="signalMin"' in html and 'id="findingType"' in html,
            "demo_case":'id="demoCase"' in html,
            "signal_index_ui":"signal_index" in js and "confidence||0" not in js
        }
    except Exception as e:
        result["ui_contract"]={"ok":False,"error":str(e)[:180]}

    # Real raster proof: render one RGB, one NBR, and one SAR tile from returned scenes.
    try:
        if s2_items:
            q=s2_items[0]
            bb=q.get("bbox") or [24.35,48.02,24.90,48.35]
            lon=(bb[0]+bb[2])/2; lat=(bb[1]+bb[3])/2
            x,y,z=_tile_xyz(lon,lat,10)
            rgb=await asyncio.to_thread(_s2_tile_sync,q["id"],"RGB",z,x,y)
            nbr=await asyncio.to_thread(_s2_tile_sync,q["id"],"NBR",z,x,y)
            result["s2_tiles"]={"ok":True,"rgb_bytes":len(rgb),"nbr_bytes":len(nbr),"zxy":[z,x,y]}
        else:
            result["s2_tiles"]={"ok":False,"reason":"no scene"}
    except Exception as e:
        result["s2_tiles"]={"ok":False,"error":str(e)[:220]}
    try:
        if s1_items:
            q=s1_items[0]
            bb=q.get("bbox") or [24.35,48.02,24.90,48.35]
            lon=(bb[0]+bb[2])/2; lat=(bb[1]+bb[3])/2
            x,y,z=_tile_xyz(lon,lat,10)
            sar=await asyncio.to_thread(_s1_tile_sync,q["id"],"vv",z,x,y)
            result["s1_tile"]={"ok":True,"bytes":len(sar),"zxy":[z,x,y]}
        else:
            result["s1_tile"]={"ok":False,"reason":"no scene"}
    except Exception as e:
        result["s1_tile"]={"ok":False,"error":str(e)[:220]}

    print("OEO_BOOT_SELFTEST "+json.dumps(result,ensure_ascii=False),flush=True)

@app.on_event("startup")
async def startup_selftest():
    asyncio.create_task(_boot_selftest())
