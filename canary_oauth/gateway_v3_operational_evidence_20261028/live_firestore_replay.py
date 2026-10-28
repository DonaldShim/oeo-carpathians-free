"""Bounded real Firestore replay. Google external provider is synthetic, labelled.
Uses the already authenticated operator in memory; never exports credentials.
Only a unique disposable collection prefix is touched.
"""
import concurrent.futures,datetime,hashlib,json,pathlib,secrets,subprocess,sys,time
ROOT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT/'source'))
from google.cloud import firestore
from google.oauth2.credentials import Credentials
from cryptography.fernet import Fernet
from gateway.firestore_store import FirestoreOAuthStore,GrantFailure
from gateway.crypto import Cipher,digest
PROJECT='project-4e9f56f4-a524-4759-91f'
GCLOUD=r'C:\Users\MeAnDeR\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
run='gw3live_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')+'_'+secrets.token_hex(3)
cert={'run_id':run,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'provider':'REAL_FIRESTORE','google_provider':'SYNTHETIC_NOT_GOOGLE_OAUTH_PROOF',
      'project':PROJECT,'runtime_identity_proof':False,'principal_class':'existing_gcloud_operator'}
client=None
try:
    credential=subprocess.run([GCLOUD,'auth','print-access-token'],capture_output=True,timeout=30,check=True).stdout.decode().strip()
    client=firestore.Client(project=PROJECT,credentials=Credentials(credential),database='(default)')
    store=FirestoreOAuthStore(PROJECT,prefix=run,client=client)
    t=int(time.time());cipher=Cipher(Fernet.generate_key().decode())
    gid='grant1';code=digest('synthetic-code');resource='https://gateway.example/mcp';cid='https://chatgpt.com/oauth/client.json'
    store.issue_code(gid,'synthetic-sub',cipher.encrypt('synthetic@example.org'),cipher.encrypt('synthetic-google-refresh'),
                     cipher.encrypt('synthetic-expired-access'),0,resource,cid,code,'challenge','https://chatgpt.com/connector_platform_oauth_redirect',t+300,t)
    def redeem(_):
        try:return ('WIN',store.redeem_code(code,'challenge','https://chatgpt.com/connector_platform_oauth_redirect',cid,resource,t,90,3600))
        except GrantFailure:return ('REJECT',None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(redeem,range(4)))
    assert sum(r[0]=='WIN' for r in results)==1
    cert['concurrent_code_redemption']={'attempts':4,'winners':1,'status':'AFFIRMED'}
    tokens=next(r[1] for r in results if r[0]=='WIN')
    def rotate(_):
        try:return ('WIN',store.rotate_refresh(digest(tokens[1]),cid,resource,t,90,3600))
        except GrantFailure:return ('REJECT',None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rotations=list(pool.map(rotate,range(4)))
    assert sum(r[0]=='WIN' for r in rotations)==1
    assert store._doc('grants',gid).get().to_dict()['revoked'] is True
    cert['concurrent_rotation_and_replay_revocation']={'attempts':4,'winners':1,'revoked':True,'status':'AFFIRMED'}
    gid='grant2'
    store.issue_code(gid,'synthetic-sub',cipher.encrypt('synthetic@example.org'),cipher.encrypt('synthetic-google-refresh'),
                     cipher.encrypt('synthetic-expired-access'),0,resource,cid,digest('code2'),'challenge','https://chatgpt.com/connector_platform_oauth_redirect',t+300,t)
    import threading
    entered=threading.Event();release=threading.Event();calls=[]
    class Google:
        def refresh(self,token):
            calls.append(1);entered.set()
            assert release.wait(10)
            return {'access_token':'synthetic-reissued','expires_in':3600}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(store.google_access,gid,cipher,Google(),t)
        assert entered.wait(10)
        try:store.google_access(gid,cipher,Google(),t);raise AssertionError('second owner admitted')
        except GrantFailure as e:assert str(e)=='refresh_in_progress'
        release.set();assert first.result(timeout=20)=='synthetic-reissued'
    assert len(calls)==1
    cert['google_refresh_lease_real_firestore']={'external_calls':1,'status':'AFFIRMED'}
    restarted=FirestoreOAuthStore(PROJECT,prefix=run,client=firestore.Client(project=PROJECT,credentials=Credentials(credential)))
    assert restarted._doc('grants',gid).get().to_dict()['refresh_status']=='IDLE'
    cert['independent_client_readback']='AFFIRMED'
    cert['status']='AFFIRMED'
except Exception as e:
    cert['status']='OPEN';cert['error_class']=type(e).__name__
finally:
    if client:
        removed=0
        try:
            for kind in ('flows','grants','codes','access','refresh','audit','rate','meta'):
                for doc in client.collection(run+'_'+kind).limit(100).stream(timeout=20):
                    doc.reference.delete(timeout=20);removed+=1
            cert['disposable_cleanup']={'deleted_new_test_documents':removed,'status':'AFFIRMED'}
        except Exception as e:cert['disposable_cleanup']={'status':'OPEN','error_class':type(e).__name__}
    path=ROOT/'evidence'/(run+'.json')
    path.write_text(json.dumps(cert,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'certificate':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'status':cert.get('status'),'error_class':cert.get('error_class')}))
sys.exit(0 if cert.get('status')=='AFFIRMED' else 1)
