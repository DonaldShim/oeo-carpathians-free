from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os, json, asyncio
import httpx
from rio_tiler.io import STACReader
from rio_tiler.colormap import cmap

ROOT = Path(__file__).parent
STATIC = ROOT / 'static'
CFG = json.loads((ROOT / 'CARPATHIANS_CONFIG.json').read_text(encoding='utf-8'))
EARTH_SEARCH = 'https://earth-search.aws.element84.com/v1'

app = FastAPI(title='OEO Карпати · Полісся 3.1 Free', version='3.2.0-free')
app.mount('/static', StaticFiles(directory=STATIC), name='static')

@app.get('/')
async def root():
    return FileResponse(STATIC / 'index.html')

@app.get('/health')
async def health():
    return {
        'monitor':'ok', 'version':'3.2.0-free', 'profile':'render-free',
        'region':'Українські Карпати + Полісся', 'stac':True,
        'sentinel1':True, 'sentinel2':True, 'nisar':True,
        'firms_configured': bool(os.getenv('FIRMS_MAP_KEY')),
        'gfw_mode':'external-evidence'
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
        results=await asyncio.to_thread(asf.search, dataset='NISAR', processingLevel='GCOV', dataMaturity='PROVISIONAL', intersectsWith=wkt, start=start, end=end, maxResults=max_results)
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

# OEO_RENDER_BOOT_SELFTEST_V1
async def _boot_selftest():
    await asyncio.sleep(2)
    bbox="24.35,48.02,24.90,48.35"
    result={"bbox":bbox}
    try:
        s1=await sentinel1(bbox=bbox,days=30,max_results=4)
        result["sentinel1"]={"ok":s1.get("ok"),"count":s1.get("count")}
    except Exception as e:
        result["sentinel1"]={"ok":False,"error":str(e)[:180]}
    try:
        s2=await sentinel2(bbox=bbox,days=30,max_results=4,cloud_max=60)
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
    print("OEO_BOOT_SELFTEST "+json.dumps(result,ensure_ascii=False),flush=True)

@app.on_event("startup")
async def startup_selftest():
    asyncio.create_task(_boot_selftest())
