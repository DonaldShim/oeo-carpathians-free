"""Verify protected, session-scoped OAuth refresh trace readback; no provider calls."""
import asyncio, json, secrets, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from canary_oauth import canary_server as s
s.READY=True
s.ISSUER='https://isolated.example.test'
s.PEPPER=secrets.token_urlsafe(48)
s.ALLOWED_EMAIL='owner@example.test'
s.dbengine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
s.Db=sessionmaker(bind=s.dbengine)
s.Base.metadata.create_all(s.dbengine)
passes=[]
def ok(label,value):assert value,label;passes.append(label)
with s.Db.begin() as db:
    f=s.Family(user_hash=s.hashed('test-identity'),client=s.PROBE_CLIENT,
       resource=s.ISSUER+'/mcp',scope='c_lab_canary.read offline_access',
       policy_hash=s.policy_binding(s.PROBE_CLIENT))
    db.add(f);db.flush();tokens=s.mint(db,f.id,f.scope)
async def read(access):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app),base_url=s.ISSUER) as c:
        r=await c.post('/mcp',headers={'Authorization':'Bearer '+access},json={
            'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'canary_control_health','arguments':{}}})
        assert r.status_code==200
        return json.loads(r.json()['result']['content'][0]['text'])
async def test():
    first=await read(tokens['access_token'])
    first_trace=first['session_oauth_audit']
    ok('trace_source',first_trace['source']=='postgresql_canary_oauth_trace_v8')
    ok('first_read_authorized',first['ok'] is True and not first['science_access'])
    ok('first_grants_zero',first_trace['refresh_grant_received']==0)
    ok('first_success_zero',first_trace['refresh_success']==0)
    ok('first_access_validated',first_trace['access_validated']==1)
    with s.Db.begin() as db:
        updated=s.rotate_refresh(db,tokens['refresh_token'],s.PROBE_CLIENT)
    ok('refresh_created',isinstance(updated,dict) and 'access_token' in updated)
    second=await read(updated['access_token'])
    trace=second['session_oauth_audit']
    ok('same_audit_session',first['audit_session']==second['audit_session'])
    ok('same_scope',first['scope']==second['scope'])
    ok('one_grant',trace['refresh_grant_received']==1)
    ok('one_success',trace['refresh_success']==1)
    ok('two_access_reads',trace['access_validated']==2)
    ok('refresh_events_in_order',[x['kind'] for x in trace['recent_refresh_events']]==['refresh_grant_received','refresh_success'])
    ok('explicit_origin_limitation',second['client_origin_proof']=='PUBLIC_CLIENT_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED')
    encoded=json.dumps(second)
    ok('no_plaintext_access',updated['access_token'] not in encoded)
    ok('no_plaintext_refresh',updated['refresh_token'] not in encoded)
    ok('no_token_refs','token_ref' not in encoded and 'encrypted_result' not in encoded)
    return {'status':'PASS_SYNTHETIC','n':len(passes),'checks':passes,
            'real_chatgpt_refresh_proof':False,'real_postgresql':False,
            'secret_values_output':False}
if __name__=='__main__':print(json.dumps(asyncio.run(test()),ensure_ascii=False,indent=2))
