"""API/state-machine verification with a linearizable in-memory Firestore stand-in.

This proves gateway handling, not real Firestore transaction behavior; an independent
live CRUD and precondition replay is required for cross-service certification.
"""
import threading, types
import pytest
from fastapi.testclient import TestClient
from urllib.parse import urlsplit, parse_qs
from cryptography.fernet import Fernet
from gateway.config import Settings
from gateway.crypto import digest, challenge_from_verifier
from gateway.firestore_store import FirestoreOAuthStore,GrantFailure
from gateway.firestore_app import create_app

class Snapshot:
    def __init__(self, x): self.exists=x is not None;self.x=dict(x) if x else {}
    def to_dict(self): return dict(self.x)
class Ref:
    def __init__(self, db, k): self.db=db;self.k=k
    def get(self, transaction=None):return Snapshot(self.db.data.get(self.k))
class Coll:
    def __init__(self, db, k): self.db=db;self.k=k
    def document(self,k):return Ref(self.db,self.k+'/'+k)
class Tx:
    def __init__(self,db):self.db=db;self.pending=[]
    def create(self,ref,data):
        if ref.k in self.db.data or any(q[1]==ref.k for q in self.pending):
            raise ValueError('ALREADY_EXISTS')
        self.pending.append(('create',ref.k,dict(data)))
    def update(self,ref,data):
        if ref.k not in self.db.data:raise ValueError('NOT_FOUND')
        self.pending.append(('update',ref.k,dict(data)))
class DB:
    def __init__(self):self.data={};self.lock=threading.RLock()
    def collection(self,k):return Coll(self,k)
    def transaction(self, **kwargs):return Tx(self)
@pytest.fixture

def store(monkeypatch):
    import google.cloud
    def transactional(fn):
        def run(tx):
            with tx.db.lock:
                result=fn(tx)
                for op,k,data in tx.pending:
                    if op=='create':tx.db.data[k]=data
                    else:tx.db.data[k].update(data)
                return result
        return run
    monkeypatch.setattr(google.cloud,'firestore',types.SimpleNamespace(transactional=transactional),raising=False)
    db=DB()
    return FirestoreOAuthStore('test-project', client=db)

class GoogleFake:
    def __init__(self):self.refresh_calls=0;self.expire_next=False
    def exchange(self,code,verifier):return {'id_token':'test-id','access_token':'google-access','refresh_token':'google-refresh','expires_in':3600}
    def verify(self,token,nonce):return {'sub':'sub-123','email':'user@example.org'}
    def refresh(self,token):
        assert token=='google-refresh'
        self.refresh_calls+=1
        return {'access_token':'google-reissued','expires_in':3600}
class UpstreamFake:
    def __init__(self):self.calls=[]
    def invoke(self,name,token):
        self.calls.append((name,token))
        return {'content':[{'type':'text','text':'test-only'}],'isError':False}

@pytest.fixture
def client(store):
    settings=Settings(public_base_url='http://127.0.0.1:8080',
        google_client_id='test.apps.googleusercontent.com',google_client_secret='test-only',
        allowed_google_email='user@example.org',gateway_encryption_key=Fernet.generate_key().decode(),
        database_url='',storage_backend='firestore',firestore_project_id='test-project',
        client_id='https://chatgpt.com/oauth/client.json',
        allowed_redirect_uris=('https://chatgpt.com/connector_platform_oauth_redirect',),
        upstream_mcp_url='http://127.0.0.1:9090/mcp',allow_sqlite_dev=True,allow_mock_upstream=True)
    google=GoogleFake(); upstream=UpstreamFake()
    with TestClient(create_app(settings,store,google,upstream),follow_redirects=False) as c:
        yield c,settings,store,google,upstream

VERIFIER='v'*63
REDIRECT='https://chatgpt.com/connector_platform_oauth_redirect'
CIMD='https://chatgpt.com/oauth/client.json'

def get_tokens(p):
    c,s,st,g,u=p
    r=c.get('/authorize',params={'response_type':'code','client_id':CIMD,'redirect_uri':REDIRECT,
       'state':'state','code_challenge':challenge_from_verifier(VERIFIER),
       'code_challenge_method':'S256','scope':'clab.read','resource':s.resource})
    assert r.status_code==302,r.text
    params=parse_qs(urlsplit(r.headers['location']).query)
    assert params['access_type']==['offline']
    cb=c.get('/google/callback',params={'state':params['state'][0],'code':'google-code'})
    assert cb.status_code==302,cb.text
    code=parse_qs(urlsplit(cb.headers['location']).query)['code'][0]
    resp=c.post('/token',data={'grant_type':'authorization_code','client_id':CIMD,
         'resource':s.resource,'redirect_uri':REDIRECT,'code':code,'code_verifier':VERIFIER})
    assert resp.status_code==200,resp.text
    return resp.json(),code

def test_end_to_end_roundtrip(client):
    c,s,store,g,u=client
    access,_=get_tokens(client)
    r=c.post('/mcp',headers={'Authorization':'Bearer '+access['access_token']},
             json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'get_fabric_health','arguments':{}}})
    assert r.status_code==200
    assert u.calls==[('get_fabric_health','google-access')]
    assert c.post('/mcp',json={'jsonrpc':'2.0','method':'tools/list','id':2}).status_code==401

def test_code_cannot_reuse(client):
    c,s,store,g,u=client
    data,code=get_tokens(client)
    q={'grant_type':'authorization_code','client_id':CIMD,'resource':s.resource,
       'redirect_uri':REDIRECT,'code':code,'code_verifier':VERIFIER}
    assert c.post('/token',data=q).status_code==400

def test_refresh_one_use_and_revocation(client):
    c,s,store,g,u=client
    data,_=get_tokens(client)
    q={'grant_type':'refresh_token','client_id':CIMD,'resource':s.resource,
       'refresh_token':data['refresh_token']}
    new=c.post('/token',data=q)
    assert new.status_code==200,new.text
    assert c.post('/token',data=q).status_code==400
    r=c.post('/mcp',headers={'Authorization':'Bearer '+new.json()['access_token']},
        json={'jsonrpc':'2.0','id':3,'method':'tools/list'})
    assert r.status_code==401

def test_write_tools_excluded(client):
    c,s,st,g,u=client
    data,_=get_tokens(client)
    headers={'Authorization':'Bearer '+data['access_token']}
    result=c.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':5,'method':'tools/call',
        'params':{'name':'recover_managed_transport','arguments':{}}})
    assert result.json()['error']['code']==-32602
    assert u.calls==[]

def test_tokens_never_stored_plaintext(client):
    c,s,st,g,u=client
    data,_=get_tokens(client)
    dumped=str(st.client.data)
    assert data['access_token'] not in dumped
    assert data['refresh_token'] not in dumped
    assert 'google-refresh' not in dumped
    assert 'google-access' not in dumped

def test_google_refresh_calls_once_and_encrypts(client):
    c,s,st,g,u=client
    data,_=get_tokens(client)
    grant_key=next(k for k in st.client.data if k.startswith('clab_gateway_v2_grants/'))
    st.client.data[grant_key]['google_access_expires']=1
    headers={'Authorization':'Bearer '+data['access_token']}
    x={'jsonrpc':'2.0','id':7,'method':'tools/call','params':{'name':'get_control_health','arguments':{}}}
    assert c.post('/mcp',headers=headers,json=x).status_code==200
    assert g.refresh_calls==1
    assert u.calls[-1]==('get_control_health','google-reissued')
    assert c.post('/mcp',headers=headers,json=x).status_code==200
    assert g.refresh_calls==1

def test_rate_limit(store):
    for n in range(12):store.admit_rate('sha',600,limit=12,window=600)
    with pytest.raises(GrantFailure):store.admit_rate('sha',600,limit=12,window=600)
    store.admit_rate('sha',1200,limit=12,window=600)

def test_concurrent_refresh_one_winner(client):
    c,s,store,g,u=client
    data,_=get_tokens(client)
    values=[]
    def fn():
        r=c.post('/token',data={'grant_type':'refresh_token','client_id':CIMD,
            'resource':s.resource,'refresh_token':data['refresh_token']})
        values.append(r.status_code)
    threads=[threading.Thread(target=fn) for _ in range(2)]
    for th in threads:th.start()
    for th in threads:th.join()
    assert sorted(values)==[200,400]

def test_invalid_code_state(client):
    c,s,st,g,u=client
    assert c.get('/google/callback',params={'code':'c','state':'bogus'}).status_code==400
    assert c.post('/token',data={'grant_type':'authorization_code','client_id':CIMD,
        'resource':s.resource,'code':'bogus','redirect_uri':REDIRECT,
        'code_verifier':VERIFIER}).status_code==400

def test_health_and_discovery(client):
    c,s,st,g,u=client
    assert c.get('/health').json()['ready'] is True
    assert c.get('/.well-known/oauth-authorization-server').json()['code_challenge_methods_supported']==['S256']
    assert c.get('/.well-known/oauth-protected-resource').json()['resource']==s.resource
