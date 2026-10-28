"""Read-only sanitized provider evidence; never collect OAuth credentials or URLs."""
import concurrent.futures,datetime,hashlib,json,pathlib,subprocess
R=pathlib.Path(__file__).parent
G=r'C:\Users\MeAnDeR\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
P='project-4e9f56f4-a524-4759-91f'
def call(args):
    p=subprocess.run([G,*args,'--format=json','--quiet'],capture_output=True,text=True,timeout=60)
    if p.returncode: return {'ok':False,'returncode':p.returncode}
    return {'ok':True,'data':json.loads(p.stdout)}
def service(name):
    x=call(['run','services','describe',name,'--region=europe-west1','--project='+P])
    if not x['ok']:return x
    d=x['data'];spec=d['spec'];status=d['status'];meta=d['metadata']
    return {'ok':True,'uid':meta.get('uid'),'generation':meta.get('generation'),
      'traffic':spec.get('traffic'),'status_traffic':status.get('traffic'),
      'latest_ready_revision':status.get('latestReadyRevisionName'),
      'configured_image':spec['template']['spec']['containers'][0]['image']}
def logs():
    query='resource.type="cloud_run_revision" AND resource.labels.service_name="c-lab-oauth-gateway-v3" AND timestamp>="2026-10-28T14:20:00Z" AND (jsonPayload.event="oauth_http" OR jsonPayload.event="google_exchange_http" OR jsonPayload.event="google_refresh_http")'
    x=call(['logging','read',query,'--project='+P,'--limit=200','--order=asc'])
    if not x['ok']:return x
    out=[]
    for e in x['data']:
        v=e.get('jsonPayload',{});path=v.get('path')
        if path is not None and path not in ('/authorize','/google/callback','/token','/revoke','/mcp'):continue
        out.append({'timestamp':e.get('timestamp'),'insert_id':e.get('insertId'),
          'revision':e.get('resource',{}).get('labels',{}).get('revision_name'),
          'event':v.get('event'),'path':path,'status':v.get('status'),'epoch':v.get('epoch')})
    return {'ok':True,'events':out,'limit':200,'not_a_full_retention_export':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    a=pool.submit(service,'c-lab-gcp-control');b=pool.submit(service,'c-lab-oauth-gateway-v3');c=pool.submit(logs)
    out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'read_only':True,
         'production':a.result(),'gateway':b.result(),'sanitized_handler_logs':c.result()}
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
p=R/'evidence'/('live-closure-'+stamp+'.json');p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
 'production':out['production'],'gateway':out['gateway'],
 'log_events':len(out['sanitized_handler_logs'].get('events',[])),
 'google_refresh_statuses':[e['status'] for e in out['sanitized_handler_logs'].get('events',[]) if e['event']=='google_refresh_http']}))
