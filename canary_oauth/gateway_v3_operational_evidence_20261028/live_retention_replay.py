import datetime,json,pathlib,subprocess,sys,time
from google.cloud import firestore
from google.oauth2.credentials import Credentials
R=pathlib.Path(__file__).parent;sys.path.insert(0,str(R/'source'))
from gateway.firestore_store import FirestoreOAuthStore
P='project-4e9f56f4-a524-4759-91f'
G=r'C:\Users\MeAnDeR\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
token=subprocess.run([G,'auth','print-access-token'],capture_output=True,timeout=30,check=True).stdout.decode().strip()
c=firestore.Client(project=P,credentials=Credentials(token))
prefix='gw3retain_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
store=FirestoreOAuthStore(P,prefix=prefix,client=c);t=int(time.time())
old=c.collection(prefix+'_codes').document('expired');fresh=c.collection(prefix+'_codes').document('fresh')
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'prefix':prefix,'provider':'REAL_FIRESTORE_OPERATOR_IDENTITY'}
try:
 old.create({'expires':t-1},timeout=10);fresh.create({'expires':t+3600},timeout=10)
 assert store.maintain(t)==1
 assert not old.get(timeout=10).exists and fresh.get(timeout=10).exists
 assert store.maintain(t+1)==0
 out.update(status='AFFIRMED',expired_deleted=1,unexpired_preserved=True,maintenance_lease_enforced=True)
except Exception as e:out.update(status='OPEN',error_class=type(e).__name__)
finally:
 for ref in (old,fresh,c.collection(prefix+'_meta').document('retention')):
  ref.delete(timeout=10)
 out['new_test_cleanup']='AFFIRMED'
 (R/'evidence'/'real-retention-replay.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps(out))
