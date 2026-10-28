"""Read-only projected OAuth evidence. Never read token/cipher or subject fields."""
import datetime,hashlib,json,pathlib,subprocess,time
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2.credentials import Credentials
R=pathlib.Path(__file__).parent;P='project-4e9f56f4-a524-4759-91f'
G=r'C:\Users\MeAnDeR\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
token=subprocess.run([G,'auth','print-access-token'],capture_output=True,timeout=30,check=True).stdout.decode().strip()
c=firestore.Client(project=P,credentials=Credentials(token))
fields=['revoked','created_epoch','google_access_expires','expires','refresh_status','refresh_fence','refresh_lease_until','client_id','resource']
grants=[]
for snap in c.collection('clab_gateway_v3_grants').select(fields).order_by('created_epoch',direction=firestore.Query.DESCENDING).limit(10).stream(timeout=15):
 data=snap.to_dict();fp=hashlib.sha256(snap.id.encode()).hexdigest()[:24]
 events=[]
 for audit in c.collection('clab_gateway_v3_audit').where(filter=FieldFilter('grant_id','==',snap.id)).select(['kind','epoch']).limit(500).stream(timeout=15):
  events.append(audit.to_dict())
 events.sort(key=lambda x:x['epoch'])
 native=[e['epoch'] for e in events if e['kind'] in ('gateway_access_and_refresh_issued','gateway_refresh_success')]
 rotations=[]
 for before,after in zip(native,native[1:]):
  rotations.append({'previous_issue_epoch':before,'refresh_epoch':after,'previous_expiry':before+90,'post_expiry':after>=before+90})
 grants.append({'grant_fingerprint':fp,'metadata':data,'events':events,'local_refresh_timing':rotations})
now=int(time.time());out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'read_only_projection':True,'credential_fields_read':False,'clock_source':'LOCAL_OPERATOR_UTC_FOR_OBSERVATION_ONLY',
 'grant_times_source':'CLOUD_RUN_HANDLER_EPOCH_FROM_FIRESTORE','gateway_access_ttl':90,'grants':grants,
 'native_browser_proof_required_separately':True}
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
p=R/'evidence'/('native-oauth-observation-'+stamp+'.json');p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'certificate':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'grant_count':len(grants),
 'grants':[{'fingerprint':g['grant_fingerprint'],'created':g['metadata'].get('created_epoch'),
 'google_access_expires':g['metadata'].get('google_access_expires'),'revoked':g['metadata'].get('revoked'),
 'events':g['events'],'refresh_timing':g['local_refresh_timing']} for g in grants]}))
