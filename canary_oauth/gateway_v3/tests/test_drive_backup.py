import json, os
import httpx
import pytest
from cryptography.fernet import Fernet
from gateway.drive_backup import encrypted_snapshot,DriveBackupTransport,DriveBackupError

def test_encrypted_snapshot_not_plaintext():
    f=Fernet.generate_key().decode()
    body,sha=encrypted_snapshot({'grants/a':{'google_refresh_cipher':'gAAAA-test-cipher',
            'client_id':'https://chatgpt.com/oauth/client.json'}},f)
    assert b'client_id' not in body
    assert sha and len(sha)==64
    assert b'gAAAA-test-cipher' in Fernet(f).decrypt(body)

def test_reject_unencrypted_secrets():
    with pytest.raises(DriveBackupError):
        encrypted_snapshot({'grant':{'refresh_token':'RAW_TOKEN'}},Fernet.generate_key().decode())


def test_drive_requires_real_delegated_token():
    with pytest.raises(DriveBackupError):DriveBackupTransport('folder').upload(b'abc','xx','')


def test_upload_and_metadata_readback_without_real_drive_credentials():
    seen=[]
    def handle(r):
        seen.append(r)
        assert r.url.host=='www.googleapis.com'
        if r.method=='GET':
            if r.url.params.get('alt')=='media':return httpx.Response(200,content=obj)
            return httpx.Response(200,json={'id':'drive-test-123','parents':['folder'],
                'size':str(len(obj)),'appProperties':{'sha256':sha}})
        assert r.url.path=='/upload/drive/v3/files'
        assert 'multipart/related;' in r.headers['content-type']
        assert b'Content-Type: application/octet-stream' in r.content
        assert b'\x00example encrypted material' in r.content
        marker=b'"name":"'
        name=r.content.split(marker)[1].split(b'"')[0].decode()
        return httpx.Response(200,json={'id':'drive-test-123','name':name,'parents':['folder'],
          'appProperties':{'sha256':__import__('hashlib').sha256(b'\x00example encrypted material').hexdigest()}})
    obj=b'\x00example encrypted material';sha=__import__('hashlib').sha256(obj).hexdigest()
    with httpx.Client(transport=httpx.MockTransport(handle)) as c:
        transport=DriveBackupTransport('folder',c)
        result=transport.upload(obj,sha,'mock-delegated-test-token')
    assert result['drive_id']=='drive-test-123'
    assert len(seen)==3
    assert result['verified_download'] is True
