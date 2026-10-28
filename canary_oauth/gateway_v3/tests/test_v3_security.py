"""Adversarial regression; all Google credentials here are synthetic fixtures."""
import hashlib
import json
import time
import pytest
from cryptography.fernet import Fernet
from gateway.crypto import Cipher, digest
from gateway.firestore_store import GrantFailure
from gateway.drive_backup import encrypted_snapshot,restore_revoked,DriveBackupError
from test_firestore_gateway import store,client,get_tokens,CIMD

def grant(client):
    c,s,st,g,u=client
    tokens,_=get_tokens(client)
    gid=st.get_grant_from_access(digest(tokens['access_token']),s.resource,int(time.time()))
    return gid,st._doc('grants',gid),Cipher(s.gateway_encryption_key)

def test_lost_google_response_requires_consent(client):
    c,s,st,g,u=client
    gid,ref,cipher=grant(client)
    st.client.data[ref.k]['google_access_expires']=0
    calls=[]
    def lost(token):calls.append(1);raise TimeoutError('synthetic transport loss')
    g.refresh=lost
    with pytest.raises(TimeoutError):st.google_access(gid,cipher,g,int(time.time()))
    assert st.client.data[ref.k]['refresh_status']=='UNKNOWN'
    with pytest.raises(GrantFailure,match='unknown'):st.google_access(gid,cipher,g,int(time.time())+100)
    assert len(calls)==1

def test_abandoned_refresh_lease_never_replays_google(client):
    c,s,st,g,u=client
    gid,ref,cipher=grant(client)
    st.client.data[ref.k].update(google_access_expires=0,refresh_status='INFLIGHT',refresh_lease_until=1)
    with pytest.raises(GrantFailure,match='unknown'):st.google_access(gid,cipher,g,int(time.time()))
    assert st.client.data[ref.k]['refresh_status']=='UNKNOWN'
    assert g.refresh_calls==0

def test_stale_completion_cannot_overwrite(client,monkeypatch):
    c,s,st,g,u=client
    gid,ref,cipher=grant(client)
    st.client.data[ref.k]['google_access_expires']=0
    t=int(time.time())
    def delayed(token):
        monkeypatch.setattr('gateway.firestore_store.time.time',lambda:t+61)
        return {'access_token':'synthetic-late','expires_in':3600}
    g.refresh=delayed
    with pytest.raises(GrantFailure,match='lease_lost'):st.google_access(gid,cipher,g,t)
    assert cipher.decrypt(st.client.data[ref.k]['google_access_cipher'])!='synthetic-late'

@pytest.mark.parametrize('name',['client_id','resource','grant_type'])
def test_duplicate_token_parameters_rejected(client,name):
    c,s,st,g,u=client
    fields={'client_id':CIMD,'resource':s.resource,'grant_type':'refresh_token'}
    from urllib.parse import urlencode
    body=urlencode(list(fields.items())+[(name,fields[name])])
    assert c.post('/token',content=body,headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==400

def test_duplicate_authorize_rejected_before_state_write(client):
    c,s,st,g,u=client
    before=dict(st.client.data)
    assert c.get('/authorize?state=a&state=b').status_code==400
    assert st.client.data==before

def test_client_secret_and_basic_rejected(client):
    c,s,st,g,u=client
    assert c.post('/token',data={'client_secret':'synthetic'}).status_code==400
    assert c.post('/token',data={},headers={'Authorization':'Basic c3ludGhldGlj'}).status_code==400

def test_revoked_grant_not_accepted_after_restart(client):
    c,s,st,g,u=client
    token,_=get_tokens(client)
    st.revoke(digest(token['refresh_token']),CIMD)
    from gateway.firestore_store import FirestoreOAuthStore
    restarted=FirestoreOAuthStore('test-project',prefix=st.prefix,client=st.client)
    with pytest.raises(GrantFailure):restarted.get_grant_from_access(digest(token['access_token']),s.resource,int(time.time()))

def test_restore_cannot_revive_access_or_google_credentials():
    key=Fernet.generate_key().decode()
    blob,sha=encrypted_snapshot({'grants/g':{'revoked':False,'client_id':CIMD,
        'google_refresh_cipher':'synthetic-encrypted','refresh_lease_owner':'old'},
        'access/old':{'expires':9999999999},'refresh/old':{'consumed':False}},key)
    restored=restore_revoked(blob,sha,key)
    assert list(restored)==['grants/g']
    assert restored['grants/g']['revoked'] is True
    assert 'google_refresh_cipher' not in restored['grants/g']
    assert restored['grants/g']['refresh_lease_owner'] is None
    with pytest.raises(DriveBackupError):restore_revoked(blob+b'X',sha,key)
    with pytest.raises(DriveBackupError):restore_revoked(blob,sha,Fernet.generate_key().decode())

def test_firestore_failure_is_closed_and_sanitized(client,monkeypatch):
    c,s,st,g,u=client
    token,_=get_tokens(client)
    def down(*a):raise RuntimeError('synthetic-private-diagnostic')
    monkeypatch.setattr(st,'get_grant_from_access',down)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+token['access_token']},json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
    assert r.status_code==503
    assert 'synthetic-private' not in r.text

def test_google_audience_issuer_nonce_subject_and_owner(client,monkeypatch):
    from google.oauth2 import id_token
    from gateway.google import GoogleProvider
    from fastapi import HTTPException
    c,s,st,g,u=client
    valid={'iss':'https://accounts.google.com','aud':s.google_client_id,'sub':'owner-sub',
           'email':s.allowed_google_email,'email_verified':True,'nonce':'nonce'}
    def verifier(token,request,aud):
        if claims.get('aud')!=aud:raise ValueError('audience')
        return claims
    monkeypatch.setattr(id_token,'verify_oauth2_token',verifier)
    for change in ({'iss':'https://evil.invalid'},{'aud':'foreign.apps.googleusercontent.com'},
                   {'sub':''},{'nonce':'foreign'},{'email':'foreign@example.org'},{'email_verified':False}):
        claims={**valid,**change}
        with pytest.raises(HTTPException):GoogleProvider(s).verify('synthetic-jwt','nonce')
    claims=valid
    assert GoogleProvider(s).verify('synthetic-jwt','nonce')['sub']=='owner-sub'
