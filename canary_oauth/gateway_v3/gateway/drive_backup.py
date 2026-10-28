"""Encrypted Google Drive offsite snapshot transport, never an OAuth transaction store.

Requires a real user-delegated OAuth access token with drive.file scope and an
existing folder created by that user. Do not try to use a naked Cloud Run
service account to own personal My Drive files (Google forbids it).
"""
from __future__ import annotations
import hashlib, json, secrets, time
import httpx
from .crypto import Cipher

class DriveBackupError(RuntimeError): pass


def encrypted_snapshot(objects: dict, fernet_key: str) -> tuple[bytes, str]:
    """Double-encrypt already encrypted/token-hashed DB records for offsite backup.

    Never accept raw token/secret fields. Backups aren't authoritative to revoke
    access; importing them must create REVOKED grants pending fresh consent.
    """
    if not isinstance(objects,dict) or len(objects)>10_000:
        raise DriveBackupError('bounded dict required')
    forbidden={'access_token','refresh_token','id_token','client_secret','private_key',
               'password','cookie','authorization','code_verifier','authorization_code','google_refresh_token'}
    def validate(obj):
        if isinstance(obj,dict):
            for k,v in obj.items():
                if str(k).lower() in forbidden:
                    raise DriveBackupError('raw credential key in snapshot')
                validate(v)
        elif isinstance(obj,(list,tuple)):
            for v in obj:validate(v)
    validate(objects)
    payload=json.dumps({'schema':'clab-gateway-v2-backup-1',
                         'created_epoch':int(time.time()),'objects':objects},
                       sort_keys=True,separators=(',',':')).encode('utf-8')
    if len(payload)>10_000_000:raise DriveBackupError('snapshot too large')
    ciphertext=Cipher(fernet_key).encrypt(payload.decode('utf-8'))
    encrypted=ciphertext.encode('ascii')
    return encrypted, hashlib.sha256(encrypted).hexdigest()


def restore_revoked(encrypted: bytes, expected_sha: str, fernet_key: str) -> dict:
    """Recover non-authoritative grant metadata, never resurrect tokens or leases.

    A separate new consent is mandatory; no access/code/refresh/flow record is
    eligible for restoration. This function does not write Firestore.
    """
    if len(encrypted)>14_000_000 or hashlib.sha256(encrypted).hexdigest()!=expected_sha:
        raise DriveBackupError('backup digest mismatch')
    try:
        payload=json.loads(Cipher(fernet_key).decrypt(encrypted.decode('ascii')))
        if payload['schema']!='clab-gateway-v2-backup-1':raise ValueError()
        objects=payload['objects']
        if not isinstance(objects,dict) or len(objects)>10000:raise ValueError()
        result={}
        for name,value in objects.items():
            if not name.startswith('grants/') or not isinstance(value,dict):continue
            safe={k:value[k] for k in ('client_id','resource','scopes','google_sub','created_epoch','expires') if k in value}
            safe.update(revoked=True,refresh_status='RECONSENT_REQUIRED',refresh_fence=0,
                        refresh_lease_owner=None,refresh_lease_until=0)
            result[name]=safe
        return result
    except Exception:
        raise DriveBackupError('invalid encrypted backup') from None


class DriveBackupTransport:
    def __init__(self, folder_id: str, client: httpx.Client|None=None):
        if not folder_id or '/' in folder_id or len(folder_id)>150:
            raise DriveBackupError('invalid Drive folder ID')
        self.folder_id=folder_id
        self.client=client or httpx.Client(timeout=20,follow_redirects=False)

    def upload(self, encrypted:bytes, digest:str, delegated_access_token:str) -> dict:
        if not delegated_access_token or len(delegated_access_token)<10:
            raise DriveBackupError('user-delegated Drive credentials unavailable')
        if hashlib.sha256(encrypted).hexdigest()!=digest:
            raise DriveBackupError('encrypted snapshot digest mismatch')
        boundary='clab_'+secrets.token_hex(12)
        filename='clab-oauth-encrypted-'+str(int(time.time()))+'-'+secrets.token_hex(4)+'.bin'
        meta={'name':filename,'parents':[self.folder_id],
              'mimeType':'application/octet-stream',
              'appProperties':{'kind':'clab-oauth-encrypted-backup','sha256':digest}}
        body=(b'--'+boundary.encode()+b'\r\n'
              +b'Content-Type: application/json; charset=UTF-8\r\n\r\n'
              +json.dumps(meta,separators=(',',':')).encode()+b'\r\n'
              +b'--'+boundary.encode()+b'\r\n'
              +b'Content-Type: application/octet-stream\r\n\r\n'
              +encrypted+b'\r\n'
              +b'--'+boundary.encode()+b'--\r\n')
        r=self.client.post('https://www.googleapis.com/upload/drive/v3/files',
              params={'uploadType':'multipart','fields':'id,name,parents,mimeType,md5Checksum,appProperties'},
              headers={'Authorization':'Bearer '+delegated_access_token,
                       'Content-Type':'multipart/related; boundary='+boundary},
              content=body)
        if r.status_code not in (200,201):
            raise DriveBackupError('Drive upload rejected: '+str(r.status_code))
        result=r.json()
        if (not result.get('id') or result.get('name')!=filename or
              self.folder_id not in result.get('parents',[]) or
              result.get('appProperties',{}).get('sha256')!=digest):
            raise DriveBackupError('Drive metadata readback mismatch')
        self.readback(result['id'],digest,delegated_access_token)
        return {'drive_id':result['id'],'filename':filename,
                'ciphertext_sha256':digest,'verified_metadata':True,'verified_download':True}

    def readback(self,file_id,expected_sha,delegated_access_token):
        import re
        if not re.fullmatch('[A-Za-z0-9_-]{1,150}',file_id):raise DriveBackupError('invalid Drive file ID')
        url='https://www.googleapis.com/drive/v3/files/'+file_id
        headers={'Authorization':'Bearer '+delegated_access_token}
        meta=self.client.get(url,headers=headers,params={'fields':'id,parents,appProperties,trashed,size'})
        if meta.status_code!=200:raise DriveBackupError('Drive independent metadata unavailable')
        data=meta.json()
        if (data.get('id')!=file_id or data.get('trashed') or self.folder_id not in data.get('parents',[]) or
            data.get('appProperties',{}).get('sha256')!=expected_sha or int(data.get('size',0))>14_000_000):
            raise DriveBackupError('Drive independent metadata mismatch')
        with self.client.stream('GET',url,headers=headers,params={'alt':'media'}) as response:
            if response.status_code!=200:raise DriveBackupError('Drive download failed')
            body=bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body)>14_000_000:raise DriveBackupError('Drive backup exceeds bound')
        if hashlib.sha256(body).hexdigest()!=expected_sha:raise DriveBackupError('Drive independent SHA mismatch')
        return bytes(body)
