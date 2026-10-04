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

ROOT = Path(__file__).parent
STATIC = ROOT / 'static'
CFG = json.loads((ROOT / 'CARPATHIANS_CONFIG.json').read_text(encoding='utf-8'))
EARTH_SEARCH = 'https://earth-search.aws.element84.com/v1'

app = FastAPI(title='OEO Карпати · Полісся 3.1 Free', version='4.1.0-free')
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
async def root():
    return FileResponse(STATIC / 'index.html')

@app.get('/health')
async def health():
    return {
        'monitor':'ok', 'version':'4.1.0-free', 'profile':'render-free',
        'region':'Українські Карпати + Полісся', 'stac':True,
        'sentinel1':True, 'sentinel2':True, 'nisar':True,
        'firms_configured': bool(os.getenv('FIRMS_MAP_KEY')),
        'gfw_mode':'external-evidence','event_engine':'sentinel2-temporal-candidates-v41'
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
      'interpretation':'Свіжі дані знайдені. NO_CONFIRMED_EVENT означає, що сам факт нових сцен не є підтвердженим природним або антропогенним событием.'
    }


# OEO_EVENT_CANDIDATES_V41
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

def _candidate_tiles_for_bbox(bbox, z=12, max_cells=9):
    minlon,minlat,maxlon,maxlat=bbox
    xa,ya=_lonlat_tile(minlon,maxlat,z)
    xb,yb=_lonlat_tile(maxlon,minlat,z)
    xs=range(min(xa,xb),max(xa,xb)+1)
    ys=range(min(ya,yb),max(ya,yb)+1)
    cx=(minlon+maxlon)/2; cy=(minlat+maxlat)/2
    tx,ty=_lonlat_tile(cx,cy,z)
    cells=[(x,y) for x in xs for y in ys]
    cells.sort(key=lambda q:(q[0]-tx)**2+(q[1]-ty)**2)
    return cells[:max_cells]

def _index_image(item_id: str, mode: str, z: int, x: int, y: int):
    mode=mode.upper()
    assets,expr,_=S2_MODE_SPEC[mode]
    with STACReader(_stac_item_url("sentinel-2-l2a",item_id)) as src:
        return src.tile(x,y,z,assets=assets,expression=expr,tilesize=96)

def _cell_change_sync(before_id: str, after_id: str, mode: str, z: int, x: int, y: int):
    import numpy as np
    a=_index_image(before_id,mode,z,x,y)
    b=_index_image(after_id,mode,z,x,y)
    av=np.asarray(a.data[0],dtype="float32")
    bv=np.asarray(b.data[0],dtype="float32")
    am=np.asarray(a.mask)>0
    bm=np.asarray(b.mask)>0
    valid=am & bm & np.isfinite(av) & np.isfinite(bv)
    if valid.sum()<200:
        return None
    delta=bv[valid]-av[valid]
    med=float(np.median(delta))
    mean=float(np.mean(delta))
    absmean=float(np.mean(np.abs(delta)))
    negfrac=float(np.mean(delta<-0.12))
    posfrac=float(np.mean(delta>0.12))
    validfrac=float(valid.mean())
    return {"median":med,"mean":mean,"absmean":absmean,"negfrac":negfrac,"posfrac":posfrac,"validfrac":validfrac}

def _scenario_rule(scenario: str, stats: dict):
    med=stats["median"]; neg=stats["negfrac"]; pos=stats["posfrac"]; ab=stats["absmean"]
    if scenario=="forest":
        severity=max(0.0,(-med-0.06)*2.2 + max(0,neg-0.12)*1.4)
        return severity>0.10, severity, "Снижение NBR: возможное повреждение/вырубка лесного покрова"
    if scenario=="fire":
        severity=max(0.0,(-med-0.08)*2.5 + max(0,neg-0.15)*1.5)
        return severity>0.12, severity, "Снижение NBR: кандидат следа пожара/повреждения"
    if scenario=="flood":
        severity=max(0.0,(med-0.05)*2.0 + max(0,pos-0.12)*1.2)
        return severity>0.10, severity, "Рост NDWI: кандидат расширения воды/переувлажнения"
    # slope / erosion screening
    severity=max(0.0,(ab-0.07)*2.0)
    return severity>0.10, severity, "Изменение NDMI: кандидат структурного изменения склона/влажности"

def _mode_for_scenario(scenario: str):
    return {"forest":"NBR","fire":"NBR","flood":"NDWI","slope":"NDMI"}.get(scenario,"NBR")

async def _pick_compare_scenes(bbox, days):
    items=await _stac_search("sentinel-2-l2a",bbox,max(days,75),18,55)
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
    before,after,items=await _pick_compare_scenes(b,days)
    events=[]
    diagnostics={"scene_count":len(items),"mode":_mode_for_scenario(scenario)}
    if before and after and before.get("id")!=after.get("id"):
        mode=_mode_for_scenario(scenario)
        cells=_candidate_tiles_for_bbox(b,12,9)
        async def one(xy):
            x,y=xy
            try:
                st=await asyncio.to_thread(_cell_change_sync,before["id"],after["id"],mode,12,x,y)
                return x,y,st
            except Exception as e:
                return x,y,{"error":str(e)[:120]}
        rows=await asyncio.gather(*(one(c) for c in cells))
        for x,y,st in rows:
            if not st or "error" in st:
                continue
            ok,severity,label=_scenario_rule(scenario,st)
            if not ok:
                continue
            bb=_tile_bounds(x,y,12)
            score=min(0.98,max(0.20,0.45+severity))
            events.append({
                "id":f"cand-{scenario}-12-{x}-{y}",
                "class":"candidate",
                "scenario":scenario,
                "title":label,
                "confidence":round(score,2),
                "status":"CANDIDATE_REQUIRES_CONFIRMATION",
                "source":"Sentinel-2 temporal index change",
                "mode":mode,
                "before":{"id":before["id"],"datetime":before.get("datetime")},
                "after":{"id":after["id"],"datetime":after.get("datetime")},
                "bbox":bb,
                "geometry":{"type":"Polygon","coordinates":[[[bb[0],bb[1]],[bb[2],bb[1]],[bb[2],bb[3]],[bb[0],bb[3]],[bb[0],bb[1]]]]},
                "metrics":{k:round(v,4) for k,v in st.items() if isinstance(v,(int,float))}
            })
        events.sort(key=lambda e:e["confidence"],reverse=True)
        diagnostics.update({"before":before.get("datetime"),"after":after.get("datetime"),"tested_cells":len(cells),"candidate_cells":len(events)})
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
            "confidence":0.99,
            "status":"DIRECT_THERMAL_ALERT",
            "source":"NASA FIRMS VIIRS",
            "geometry":{"type":"Point","coordinates":[lon,lat]},
            "point":[lon,lat],
            "date":p.get("date"),"time":p.get("time"),"frp":p.get("frp"),"firms_confidence":p.get("confidence")
        })
    return {
        "ok":True,
        "scenario":scenario,
        "events":events,
        "count":len(events),
        "direct_count":sum(1 for e in events if e["class"]=="direct"),
        "candidate_count":sum(1 for e in events if e["class"]=="candidate"),
        "firms_configured":bool(os.getenv("FIRMS_MAP_KEY")),
        "gfw_mode":"external-evidence",
        "diagnostics":diagnostics,
        "warning":"Candidate events are screening signals, not confirmed incidents. Direct FIRMS points are thermal alerts."
    }

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
