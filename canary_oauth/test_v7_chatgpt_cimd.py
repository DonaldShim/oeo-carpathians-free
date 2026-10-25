"""Offline contract tests for proposed ChatGPT CIMD integration. No real ChatGPT calls."""
import os,sys,json,secrets,asyncio,base64,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from canary_oauth import canary_server as s
s.READY=True
s.ISSUER='https://c-lab-oauth-canary-20261025.onrender.com'
s.ALLOWED_EMAIL='test@invalid.example'
s.PEPPER=secrets.token_urlsafe(48)
s.dbengine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
s.Db=sessionmaker(bind=s.dbengine)
s.Base.metadata.create_all(s.dbengine)
checks=[]
def ck(n,c):
    assert c,n
    checks.append(n)
def message(method,params=None):
    return {'jsonrpc':'2.0','id':14,'method':method,'params':params or {}}
async def test():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app),base_url=s.ISSUER,follow_redirects=False) as c:
        meta=(await c.get('/.well-known/oauth-authorization-server')).json()
        ck('cimd_advertised',meta['client_id_metadata_document_supported'] is True)
        ck('public_pkce_none_supported',meta['token_endpoint_auth_methods_supported']==['none'])
        init=await c.post('/mcp',json=message('initialize',{'protocolVersion':'2025-03-26'}))
        ck('anonymous_initialize',init.status_code==200)
        listing=await c.post('/mcp',json=message('tools/list'))
        t=listing.json()['result']['tools'][0]
        ck('anonymous_tool_discovery',listing.status_code==200 and t['name']=='canary_control_health')
        ck('tool_scoped_oauth',t['securitySchemes']==[{'type':'oauth2','scopes':['c_lab_canary.read']}])
        no=await c.post('/mcp',json=message('tools/call',{'name':'canary_control_health','arguments':{}}))
        ck('runtime_meta_linking_challenge',no.status_code==200 and no.json()['result']['isError'] and bool(no.json()['result']['_meta']['mcp/www_authenticate']))
        bad=await c.post('/mcp',json=message('tools/call',{'name':'canary_control_health','arguments':{}}),headers={'Authorization':'Bearer malformed'})
        ck('bad_token_never_validated',bad.status_code==200 and bad.json()['result']['isError'])
        with s.Db.begin() as db:
            fam=s.Family(user_hash=s.hashed('mock-user'),client=s.OPENAI_CIMD,resource=s.ISSUER+'/mcp',scope='c_lab_canary.read offline_access',policy_hash=s.policy_binding(s.OPENAI_CIMD))
            db.add(fam);db.flush()
            pair=s.mint(db,fam.id,fam.scope)
        ok=await c.post('/mcp',json=message('tools/call',{'name':'canary_control_health','arguments':{}}),headers={'Authorization':'Bearer '+pair['access_token']})
        ck('cimd_protected_mcp_read',ok.status_code==200 and ok.json()['result']['isError'] is False)
        verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        p=dict(response_type='code',client_id=s.OPENAI_CIMD,redirect_uri=s.CALLBACK,resource=s.ISSUER+'/mcp',code_challenge=challenge,code_challenge_method='S256',scope='c_lab_canary.read offline_access',state=secrets.token_urlsafe(12))
        real_get=s.httpx.get
        class Fake:
            def raise_for_status(self):pass
            def json(self):return {'client_id':s.OPENAI_CIMD,'redirect_uris':[s.CALLBACK],'token_endpoint_auth_methods_supported':['none','private_key_jwt']}
        s.httpx.get=lambda *a,**k:Fake()
        try:
            good=await c.get('/authorize',params=p)
            ck('cimd_pinned_metadata_admission',good.status_code==302 and 'accounts.google.com' in good.headers['location'])
            invalid=await c.get('/authorize',params={**p,'redirect_uri':'http://localhost:5/callback'})
            ck('cimd_wrong_redirect_blocked',invalid.status_code==400)
            s.httpx.get=lambda *a,**k: type('FakeBad',(),{'raise_for_status':lambda self:None,'json':lambda self:{'client_id':'wrong','redirect_uris':[]}})()
            rejected=await c.get('/authorize',params=p)
            ck('cimd_wrong_document_blocked',rejected.status_code==400)
        finally:s.httpx.get=real_get
        ck('legacy_clients_retained',s.CLIENT in s.CLIENTS and s.PROBE_CLIENT in s.CLIENTS)
    return {'status':'AFFIRMED_SYNTHETIC','checks':checks,'count':len(checks),'real_chatgpt_flow':False,'real_google_login':False,'live_canary_changed':False}
if __name__=='__main__':
    print(json.dumps(asyncio.run(test()),indent=2))
