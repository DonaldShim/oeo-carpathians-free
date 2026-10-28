import json
from urllib.parse import urlsplit,parse_qs
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from gateway.config import Settings
from gateway.crypto import challenge_from_verifier
from gateway.app import create_app
from sqlalchemy.orm import Session
from sqlalchemy import select
from gateway.db import Flow, Grant, AccessToken, RefreshToken, Audit

VERIFIER='v'*63
REDIRECT='https://chatgpt.com/connector_platform_oauth_redirect'
CIMD='https://chatgpt.com/oauth/client.json'

class MockGoogle:
    def __init__(self):
        self.calls=[]
        self.has_refresh=True
        self.refresh_calls=0
        self.email='tester@example.org'
    def exchange(self,code,verifier):
        self.calls.append((code,verifier))
        data={'access_token':'goog-access-new','id_token':'stub','expires_in':3600}
        if self.has_refresh:
            data['refresh_token']='goog-refresh-new'
        return data
    def verify(self,token,nonce):
        return {'sub':'1234','email':self.email,'email_verified':True,'nonce':nonce}
    def refresh(self,token):
        assert token=='goog-refresh-new'
        self.refresh_calls+=1
        return {'access_token':'goog-refreshed','expires_in':3600}

class MockUpstream:
    def __init__(self):self.calls=[]
    def invoke(self,name,token):
        self.calls.append((name,token))
        return {'content':[{'type':'text','text':json.dumps({'tool':name,'ok':True})}],'isError':False}

@pytest.fixture()
def env(tmp_path):
    from gateway.config import Settings
    settings=Settings(public_base_url='http://127.0.0.1:8080',
        google_client_id='mock-client.apps.googleusercontent.com',
        google_client_secret='mock-secret-in-test-only',
        allowed_google_email='tester@example.org',
        gateway_encryption_key=Fernet.generate_key().decode(),
        database_url='sqlite:///'+str(tmp_path/'oauth.sqlite'),
        client_id=CIMD,allowed_redirect_uris=(REDIRECT,),
        upstream_mcp_url='http://127.0.0.1:9090/mcp',
        allow_sqlite_dev=True,allow_mock_upstream=True,access_lifetime_seconds=300)
    provider=MockGoogle()
    upstream=MockUpstream()
    app=create_app(settings,provider,upstream,create_schema=True)
    with TestClient(app,follow_redirects=False) as client:
        yield client, settings, provider, upstream, app

def params(settings):
    return {'response_type':'code','client_id':CIMD,'redirect_uri':REDIRECT,'state':'clientsecretstate',
            'scope':'clab.read','resource':settings.resource,
            'code_challenge':challenge_from_verifier(VERIFIER),
            'code_challenge_method':'S256'}

def authorizes(env):
    client, settings, provider, _, app=env
    r=client.get('/authorize',params=params(settings))
    assert r.status_code==302
    return parse_qs(urlsplit(r.headers['location']).query)

def grants(env):
    client,settings,*_=env
    redirect=authorizes(env)
    cb=client.get('/google/callback',params={'state':redirect['state'][0],'code':'google-code'})
    assert cb.status_code==302
    query=parse_qs(urlsplit(cb.headers['location']).query)
    r=client.post('/token',data={'grant_type':'authorization_code','client_id':CIMD,
        'redirect_uri':REDIRECT,'resource':settings.resource,'code':query['code'][0],
        'code_verifier':VERIFIER})
    assert r.status_code==200,r.text
    return r.json(),query

def test_oauth_metadata_and_private_resource(env):
    client,settings,*_=env
    res=client.get('/.well-known/oauth-protected-resource').json()
    meta=client.get('/.well-known/oauth-authorization-server').json()
    assert res['resource']==settings.resource
    assert res['authorization_servers']==[settings.public_base_url]
    assert meta['code_challenge_methods_supported']==['S256']
    assert meta['authorization_response_iss_parameter_supported'] is True
    assert meta['token_endpoint_auth_methods_supported']==['none']
    r=client.get('/mcp')
    assert r.status_code==401
    assert 'resource_metadata=' in r.headers['www-authenticate']

def test_google_redirect_offline_and_pkce(env):
    p=authorizes(env)
    assert p['access_type']==['offline']
    assert p['prompt']==['consent']
    assert p['redirect_uri']==[env[1].google_callback]
    assert p['code_challenge_method']==['S256']
    assert 'nonce' in p
    assert p['scope']==['openid email profile']

def test_strict_authorize_params(env):
    client,settings,*_=env
    for change in ({'resource':'https://other.example/mcp'}, {'redirect_uri':'https://evil.example/cb'},
                   {'client_id':'https://evil.example/client.json'},{'code_challenge_method':'plain'},
                   {'scope':'clab.write'}, {'response_type':'token'},{'state':''}):
        p=params(settings);p.update(change)
        assert client.get('/authorize',params=p).status_code==400

def test_one_time_google_state(env):
    client,settings,provider,*_=env
    p=authorizes(env);gstate=p['state'][0]
    first=client.get('/google/callback',params={'state':gstate,'code':'c'})
    assert first.status_code==302
    second=client.get('/google/callback',params={'state':gstate,'code':'c'})
    assert second.status_code==400
    assert len(provider.calls)==1

def test_no_google_refresh_refuses_to_issue_code(env):
    client,settings,provider,*_=env
    provider.has_refresh=False
    p=authorizes(env)
    r=client.get('/google/callback',params={'state':p['state'][0],'code':'c'})
    assert r.status_code==403
    with Session(env[4].state.engine) as s:
        assert len(s.execute(select(Grant)).scalars().all())==0

def test_auth_code_pkce_and_single_use(env):
    client,settings,*_=env
    p=authorizes(env)
    cb=client.get('/google/callback',params={'state':p['state'][0],'code':'c'})
    code=parse_qs(urlsplit(cb.headers['location']).query)['code'][0]
    body={'grant_type':'authorization_code','client_id':CIMD,'redirect_uri':REDIRECT,
          'resource':settings.resource,'code':code,'code_verifier':'a'*43}
    assert client.post('/token',data=body).status_code==400
    body['code_verifier']=VERIFIER
    assert client.post('/token',data=body).status_code==200
    assert client.post('/token',data=body).status_code==400

def test_client_resource_enforced_at_token(env):
    client,settings,*_=env
    p=authorizes(env)
    cb=client.get('/google/callback',params={'state':p['state'][0],'code':'c'})
    code=parse_qs(urlsplit(cb.headers['location']).query)['code'][0]
    body={'grant_type':'authorization_code','client_id':CIMD,'redirect_uri':REDIRECT,
          'resource':'https://evil.example/mcp','code':code,'code_verifier':VERIFIER}
    assert client.post('/token',data=body).status_code==400
    body['resource']=settings.resource
    body['redirect_uri']='https://evil.example/cb'
    assert client.post('/token',data=body).status_code==400

def test_mcp_only_three_read_tools(env):
    client,settings,provider,upstream,app=env
    data,_=grants(env)
    headers={'Authorization':'Bearer '+data['access_token']}
    def req(id,method,params=None):
        return client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':id,'method':method,'params':params or {}})
    init=req(1,'initialize',{'protocolVersion':'2025-06-18'})
    assert init.status_code==200
    items=req(2,'tools/list').json()['result']['tools']
    assert sorted(x['name'] for x in items)==['get_control_health','get_controller_status','get_fabric_health']
    assert all(x['annotations']['readOnlyHint'] for x in items)
    assert req(3,'tools/call',{'name':'recover_managed_transport','arguments':{}}).json()['error']['code']==-32602
    assert req(4,'tools/call',{'name':'get_control_health','arguments':{'arbitrary':'x'}}).json()['error']['code']==-32602
    good=req(5,'tools/call',{'name':'get_control_health','arguments':{}})
    assert good.status_code==200
    assert upstream.calls==[('get_control_health','goog-access-new')]
    assert 'get_control_health' in str(good.json())
    assert client.post('/mcp',json={'jsonrpc':'2.0','id':9,'method':'tools/list'}).status_code==401

def test_refresh_rotation_and_replay_revokes_grant(env):
    client,settings,*_=env
    data,_=grants(env)
    base={'grant_type':'refresh_token','client_id':CIMD,'resource':settings.resource}
    response=client.post('/token',data={**base,'refresh_token':data['refresh_token']})
    assert response.status_code==200
    issued=response.json()
    assert issued['refresh_token'] != data['refresh_token']
    replay=client.post('/token',data={**base,'refresh_token':data['refresh_token']})
    assert replay.status_code==400
    assert client.post('/token',data={**base,'refresh_token':issued['refresh_token']}).status_code==400
    assert client.post('/mcp',headers={'Authorization':'Bearer '+issued['access_token']},json={
        'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401
    with Session(env[4].state.engine) as s:
        assert s.execute(select(Audit).where(Audit.kind=='refresh_replay_grant_revoked')).first() is not None

def test_google_access_refresh_happens_only_on_stale_cache(env):
    client,settings,provider,upstream,app=env
    data,_=grants(env)
    with Session(app.state.engine) as s,s.begin():
        grant=s.execute(select(Grant)).scalar_one()
        grant.google_access_expires=1
    headers={'Authorization':'Bearer '+data['access_token']}
    r=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call',
        'params':{'name':'get_fabric_health','arguments':{}}})
    assert r.status_code==200
    assert provider.refresh_calls==1
    assert upstream.calls[-1]==('get_fabric_health','goog-refreshed')
    with Session(app.state.engine) as s:
        assert s.execute(select(Audit).where(Audit.kind=='google_refresh_success')).first() is not None

def test_ciphertexts_not_plain_google_credentials(env):
    client,settings,provider,upstream,app=env
    data,_=grants(env)
    with Session(app.state.engine) as s:
        g=s.execute(select(Grant)).scalar_one()
        assert 'goog-refresh-new' not in g.google_refresh_cipher
        assert 'goog-access-new' not in g.google_access_cipher
        assert g.resource==settings.resource
        assert g.scopes=='clab.read'
        assert s.execute(select(RefreshToken)).scalar_one().token_hash != data['refresh_token']
        assert s.execute(select(AccessToken)).scalar_one().token_hash != data['access_token']

def test_invalid_configuration_fails_closed(tmp_path):
    from dataclasses import replace
    settings=Settings(public_base_url='http://127.0.0.1:8080',google_client_id='mock-client.apps.googleusercontent.com',
        google_client_secret='x',allowed_google_email='tester@example.org',gateway_encryption_key=Fernet.generate_key().decode(),
        database_url='sqlite:///'+str(tmp_path/'test.db'),client_id=CIMD,allowed_redirect_uris=(REDIRECT,),
        upstream_mcp_url='http://127.0.0.1:9090/mcp',allow_sqlite_dev=True)
    with pytest.raises(ValueError):replace(settings,allow_sqlite_dev=False)
    with pytest.raises(ValueError):replace(settings,allowed_redirect_uris=('https://bad.test/cb?token=a',))
    with pytest.raises(ValueError):replace(settings,allow_sqlite_dev=False,allow_mock_upstream=True)

def test_state_invalid_and_callback_error_issuer(env):
    client,settings,*_=env
    assert client.get('/google/callback',params={'state':'not-a-state','code':'c'}).status_code==400
    p=authorizes(env)
    response=client.get('/google/callback',params={'state':p['state'][0],'error':'access_denied'})
    assert response.status_code==302
    vals=parse_qs(urlsplit(response.headers['location']).query)
    assert vals=={'state':['clientsecretstate'],'error':['access_denied'],'iss':[settings.public_base_url]}

def test_revoked_and_expired_access_denied(env):
    client,settings,provider,upstream,app=env
    tokens,_=grants(env)
    with Session(app.state.engine) as s,s.begin():
        row=s.execute(select(AccessToken)).scalar_one()
        row.expires=1
    response=client.post('/mcp',headers={'Authorization':'Bearer '+tokens['access_token']},json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
    assert response.status_code==401
    assert len(upstream.calls)==0

def test_post_json_size_cap_and_malformed_json(env):
    client,settings,provider,upstream,app=env
    tokens,_=grants(env)
    hdr={'Authorization':'Bearer '+tokens['access_token']}
    assert client.post('/mcp',headers=hdr,content=b'{'*70000).status_code==413
    assert client.post('/mcp',headers=hdr,content=b'not-json').status_code==400
    assert not upstream.calls

def test_unknown_gateway_token_rejected(env):
    client,settings,provider,upstream,app=env
    for method in ('GET','POST'):
        if method=='GET':r=client.get('/mcp',headers={'Authorization':'Bearer deadbeef'})
        else:r=client.post('/mcp',headers={'Authorization':'Bearer deadbeef'},json={})
        assert r.status_code==401
    assert upstream.calls==[]

def test_health_requires_durable_schema(env):
    client,*_=env
    h=client.get('/health')
    assert h.status_code==200
    assert h.json()['ready'] is True
    assert h.json()['google_authorization_verified'] is False

def test_rfc7009_revocation_invalidates_whole_grant(env):
    client,settings,*_=env
    tokens,_=grants(env)
    response=client.post('/revoke',data={'client_id':CIMD,'token':tokens['refresh_token']})
    assert response.status_code==200
    assert client.post('/mcp',headers={'Authorization':'Bearer '+tokens['access_token']},json={
        'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==401
    assert client.post('/token',data={'grant_type':'refresh_token','client_id':CIMD,
        'resource':settings.resource,'refresh_token':tokens['refresh_token']}).status_code==400
    # RFC7009: unknown token is still a 200, no token-existence oracle.
    assert client.post('/revoke',data={'client_id':CIMD,'token':'not-a-real-token'}).status_code==200
    assert client.post('/revoke',data={'client_id':'https://other.example',
        'token':'not-a-real-token'}).status_code==400


def test_unauthenticated_mcp_advertises_both_auth_challenges(env):
    client, settings, provider, upstream, app = env
    r = client.post('/mcp',json={
        'jsonrpc':'2.0', 'id':1, 'method':'tools/call',
        'params':{'name':'get_control_health','arguments':{}}})
    assert r.status_code == 401
    header = r.headers['www-authenticate']
    meta = r.json()['_meta']['mcp/www_authenticate']
    assert meta == [header]
    assert 'error="invalid_token"' in header
    assert 'error_description=' in header
    assert settings.public_base_url+'/.well-known/oauth-protected-resource' in header
    assert upstream.calls == []
