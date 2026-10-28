import datetime,hashlib,json,pathlib,subprocess,sys
from google.cloud import firestore
from google.oauth2.credentials import Credentials
R=pathlib.Path(__file__).parent;sys.path.insert(0,str(R/'source'))
from gateway.drive_backup import restore_revoked
from gateway.firestore_store import FirestoreOAuthStore,GrantFailure
from gateway.crypto import digest
P='project-4e9f56f4-a524-4759-91f'
G=r'C:\Users\MeAnDeR\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
expected='70869bffa1158d0df9111a84467784e7db65598b657a2511337e5ce944ff6110'
f=pathlib.Path(r'C:\Users\MeAnDeR\Downloads\clab-gateway-v3-encrypted-'+expected+'.bin')
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'dataset':'SYNTHETIC_REVOKED_GRANT_ONLY',
 'drive_file_id':'1B1bQjUzD3ntIttLbdUSNqyvu4ImL99do','folder_id':'1nvWdPEWl8_Gi2B5xrnaZ1osNpeAq2Jt8',
 'independent_readback_channel':'OFFICIAL_DRIVE_BROWSER_DOWNLOAD','ciphertext_sha256':expected,
 'runtime_drive_delegation':'NOT_PROVEN_CONNECTOR_OPERATOR_BACKUP_ONLY'}
ref=None
try:
    raw=f.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected and len(raw)==696
    q=subprocess.run([G,'secrets','versions','access','1','--secret=clab-gateway-v3-backup-key','--project='+P],capture_output=True,timeout=30,check=True)
    key=q.stdout.decode().strip()
    restored=restore_revoked(raw,expected,key)
    assert len(restored)==1
    data=restored['grants/revoked-probe'];assert data['revoked'] is True
    assert 'google_refresh_cipher' not in data
    token=subprocess.run([G,'auth','print-access-token'],capture_output=True,timeout=30,check=True).stdout.decode().strip()
    client=firestore.Client(project=P,credentials=Credentials(token))
    prefix='gw3restore_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
    ref=client.collection(prefix+'_grants').document('restored-revoked-probe')
    ref.create(data,timeout=20)
    independent=firestore.Client(project=P,credentials=Credentials(token))
    snap=independent.collection(prefix+'_grants').document('restored-revoked-probe').get(timeout=20)
    assert snap.to_dict()==data
    store=FirestoreOAuthStore(P,prefix=prefix,client=independent)
    try:store.get_grant_from_access(digest('SYNTHETIC_OLD_BEARER'),data['resource'],int(datetime.datetime.now().timestamp()));raise AssertionError('old token restored')
    except GrantFailure:pass
    out.update(status='AFFIRMED_TEST_DATA_BACKUP_AND_RESTORE',download_bytes=len(raw),
      authenticated_decryption=True,restored_grants=1,all_grants_revoked=True,
      google_credentials_restored=False,old_access_rejected=True,independent_firestore_readback=True)
except Exception as e:out.update(status='OPEN',error_class=type(e).__name__)
finally:
    if ref:
        try:ref.delete(timeout=20);out['new_restore_probe_cleanup']='AFFIRMED'
        except Exception:out['new_restore_probe_cleanup']='OPEN'
    path=R/'evidence'/'drive-live-restore-certificate.json';path.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({**out,'certificate_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
