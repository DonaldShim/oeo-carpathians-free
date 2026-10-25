"""Isolated C-Lab OAuth Canary. No C-Fabric tools, fail closed by default."""
import os, time, hmac, hashlib, base64, secrets, json, re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from urllib.parse import urlencode, parse_qs
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, select, text, func
from sqlalchemy.orm import declarative_base, sessionmaker
import jwt, httpx

Base=declarative_base()
class Intent(Base):
    __tablename__='canary_auth_intent'
    client=Column(String(128),nullable=False,default='clab-canary-chatgpt-20261025',server_default='clab-canary-chatgpt-20261025')
    redirect=Column(String(512),nullable=False,default='https://chatgpt.com/connector_platform_oauth_redirect',server_default='https://chatgpt.com/connector_platform_oauth_redirect')
    id=Column(Integer,primary_key=True)
    state_hash=Column(String(64),unique=True,nullable=False)
    nonce_hash=Column(String(64),nullable=False)
    client_state=Column(String(512),nullable=False)
    challenge=Column(String(128),nullable=False)
    scope=Column(String(128),nullable=False)
    expires=Column(Integer,nullable=False)
    used=Column(Boolean,default=False,nullable=False)
class Code(Base):
    __tablename__='canary_auth_code'
    client=Column(String(128),nullable=False,default='clab-canary-chatgpt-20261025',server_default='clab-canary-chatgpt-20261025')
    redirect=Column(String(512),nullable=False,default='https://chatgpt.com/connector_platform_oauth_redirect',server_default='https://chatgpt.com/connector_platform_oauth_redirect')
    id=Column(Integer,primary_key=True)
    code_hash=Column(String(64),unique=True,nullable=False)
    user_hash=Column(String(64),nullable=False)
    challenge=Column(String(128),nullable=False)
    scope=Column(String(128),nullable=False)
    expires=Column(Integer,nullable=False)
    used=Column(Boolean,default=False,nullable=False)
class Family(Base):
    __tablename__='canary_family'
    id=Column(Integer,primary_key=True)
    user_hash=Column(String(64),nullable=False)
    client=Column(String(128),nullable=False)
    resource=Column(String(512),nullable=False)
    scope=Column(String(128),nullable=False,default='c_lab_canary.read',server_default='c_lab_canary.read')
    policy_hash=Column(String(64),nullable=False,default='',server_default='')
    revoked=Column(Boolean,default=False,nullable=False)
class Token(Base):
    __tablename__='canary_token'
    id=Column(Integer,primary_key=True)
    hashed=Column(String(64),unique=True,nullable=False)
    kind=Column(String(16),nullable=False)
    family=Column(Integer,ForeignKey('canary_family.id'),nullable=False)
    expires=Column(Integer,nullable=False)
    consumed_at=Column(Integer,nullable=True)
class RefreshRecovery(Base):
    """Encrypted bounded receipt, accessible only with old bearer AND a secret client attempt nonce."""
    __tablename__='canary_refresh_recovery'
    old_token_id=Column(Integer,ForeignKey('canary_token.id'),primary_key=True)
    attempt_hash=Column(String(64),nullable=False)
    encrypted_result=Column(String(4096),nullable=False)
    nonce=Column(String(32),nullable=False)
    expires=Column(Integer,nullable=False)
    successor_refresh_hash=Column(String(64),nullable=False)

class FaultOnce(Base):
    """One exact operator-configured canary failure; immutable consumed marker."""
    __tablename__='canary_fault_once_v8'
    run_id=Column(String(128),primary_key=True)
    session_ref=Column(String(64),nullable=False)
    epoch=Column(Integer,nullable=False)
    had_idempotency=Column(Boolean,nullable=False)

class OAuthTrace(Base):
    """Append-only sanitized request evidence; never bearer/assertion/code material."""
    __tablename__='canary_oauth_trace_v8'
    seq=Column(Integer,primary_key=True)
    kind=Column(String(32),nullable=False)
    epoch=Column(Integer,nullable=False)
    session_ref=Column(String(64),nullable=False)
    token_ref=Column(String(64),nullable=True)
    client=Column(String(128),nullable=False)
    client_auth=Column(String(32),nullable=False)
    token_expires=Column(Integer,nullable=True)

class Event(Base):
    __tablename__='canary_event'
    name=Column(String(64),primary_key=True)
    total=Column(Integer,default=0,nullable=False)

class RateLimit(Base):
    __tablename__='canary_rate_limit'
    key=Column(String(64),primary_key=True)
    total=Column(Integer,nullable=False)
    expires=Column(Integer,nullable=False)

ISSUER=os.environ.get('CANARY_ISSUER','').rstrip('/')
CLIENT='clab-canary-chatgpt-20261025'
CALLBACK='https://chatgpt.com/connector_platform_oauth_redirect'
PROBE_CLIENT='C_LAB_OAUTH_PROBE_V1'
PROBE_CALLBACK='http://127.0.0.1:8769/callback'
OPENAI_CIMD='https://chatgpt.com/oauth/client.json'
CLIENTS={CLIENT:CALLBACK,PROBE_CLIENT:PROBE_CALLBACK,OPENAI_CIMD:CALLBACK}
GOOGLE_ID=os.environ.get('GOOGLE_OAUTH_CLIENT_ID','')
GOOGLE_SECRET=os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET','')
ALLOWED_EMAIL=os.environ.get('GOOGLE_ALLOWED_EMAIL','').lower().strip()
DATABASE_URL=os.environ.get('DATABASE_URL','')
PEPPER=os.environ.get('TOKEN_HASH_PEPPER','')
READY=(os.environ.get('CANARY_OAUTH_ENABLED')=='1' and ISSUER.startswith('https://') and
       GOOGLE_ID and GOOGLE_SECRET and ALLOWED_EMAIL and len(PEPPER)>=32 and
       DATABASE_URL.startswith(('postgres://','postgresql://','postgresql+psycopg://')))
dbengine=create_engine(("postgresql+psycopg://"+DATABASE_URL.split("://",1)[1] if DATABASE_URL.startswith(('postgres://','postgresql://')) else DATABASE_URL),pool_pre_ping=True,connect_args={"connect_timeout":5,"options":"-c statement_timeout=5000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=5000"}) if DATABASE_URL.startswith(('postgres://','postgresql://','postgresql+psycopg://')) else None
Db=sessionmaker(bind=dbengine) if dbengine is not None else None
app=FastAPI(title='C-Lab OAuth Canary',docs_url=None,redoc_url=None,openapi_url=None)

@app.on_event('startup')
def prepare():
    if dbengine is not None:
        Base.metadata.create_all(dbengine)
    if os.environ.get('CANARY_V6_STARTUP_PG_AUDIT')=='1':
        import threading
        def isolated_audit():
            try:
                from .v6_postgres_replay import run
                report=run(__import__(__name__,fromlist=['Base']))
                clean={k:report.get(k) for k in ('status','backend','checks','check_count','concurrency','engine_reconstruction','isolated_schema_removed','live_token_tables_mutated','failure_class','failed_check','elapsed_seconds')}
                print('CANARY_V6_PG_CERT '+json.dumps(clean,separators=(',',':')),flush=True)
            except Exception as e:
                print('CANARY_V6_PG_CERT '+json.dumps({'status':'REJECTED','failure_class':type(e).__name__,'secret_exposed':False}),flush=True)
        threading.Thread(target=isolated_audit,name='canary-v6-postgres-isolated-audit',daemon=True).start()

        # Additive migration; existing ChatGPT intents/codes keep their original binding.
        with dbengine.begin() as db:
            for table in ('canary_auth_intent','canary_auth_code'):
                db.execute(text("ALTER TABLE "+table+" ADD COLUMN IF NOT EXISTS client VARCHAR(128) NOT NULL DEFAULT 'clab-canary-chatgpt-20261025'"))
                db.execute(text("ALTER TABLE "+table+" ADD COLUMN IF NOT EXISTS redirect VARCHAR(512) NOT NULL DEFAULT 'https://chatgpt.com/connector_platform_oauth_redirect'"))
def clock():return int(time.time())
def fresh():return secrets.token_urlsafe(40)
def hashed(value):return hmac.new(PEPPER.encode(),value.encode(),hashlib.sha256).hexdigest()
def error(code,name):
    headers={'Cache-Control':'no-store'}
    if code==401 and name=='unauthorized':headers['WWW-Authenticate']='Bearer error="invalid_token", resource_metadata="'+ISSUER+'/.well-known/oauth-protected-resource/mcp"'
    return JSONResponse({'error':name},status_code=code,headers=headers)
def count(db,name):
    assert name in ('refresh_token_issued','refresh_grant_received','refresh_success','access_validated')
    db.execute(text('INSERT INTO canary_event(name,total) VALUES (:n,1) ON CONFLICT (name) DO UPDATE SET total=canary_event.total+1'),{'n':name})
def policy_binding(client=CLIENT):return hashed(ALLOWED_EMAIL+'|'+client+'|'+ISSUER+'/mcp')

def session_ref(fid):return hashed('canary-v8-session:'+str(fid))
def trace(db,kind,fid,token_hash=None,expires=None,client_auth='none'):
    assert kind in ('refresh_token_issued','refresh_grant_received','refresh_success','access_validated','access_expired','refresh_retry_bound','refresh_reply_suppressed')
    fam=db.get(Family,fid)
    assert fam is not None
    db.add(OAuthTrace(kind=kind,epoch=clock(),session_ref=session_ref(fid),
        token_ref=hashed('canary-v8-token:'+token_hash) if token_hash else None,
        client=fam.client,client_auth=client_auth,token_expires=expires))


def mint(db,fid,scope='c_lab_canary.read offline_access'):
    at,rt=fresh(),fresh()
    db.add(Token(hashed=hashed(at),kind='access',family=fid,expires=clock()+90))
    result={'access_token':at,'token_type':'Bearer','expires_in':90,'scope':scope}
    if 'offline_access' in scope.split():
        db.add(Token(hashed=hashed(rt),kind='refresh',family=fid,expires=clock()+86400))
        count(db,'refresh_token_issued')
        trace(db,'refresh_token_issued',fid,hashed(at),clock()+90)
        result['refresh_token']=rt
    return result
@app.get('/healthz')
def health():return {'service':'c-lab-oauth-canary','ready':bool(READY),'science_access':False}
@app.get('/.well-known/oauth-authorization-server')
def metadata():
    return {'issuer':ISSUER or 'https://disabled.invalid','authorization_endpoint':ISSUER+'/authorize',
      'token_endpoint':ISSUER+'/token','grant_types_supported':['authorization_code','refresh_token'],
      'response_types_supported':['code'],'code_challenge_methods_supported':['S256'],
      'authorization_response_iss_parameter_supported':True,
      'client_id_metadata_document_supported':True,
      'token_endpoint_auth_methods_supported':['none'],
      'scopes_supported':['c_lab_canary.read','offline_access']}
@app.get('/.well-known/oauth-protected-resource')
@app.get('/.well-known/oauth-protected-resource/mcp')
def resource_metadata():
    return {'resource':ISSUER+'/mcp','authorization_servers':[ISSUER or 'https://disabled.invalid'],
            'scopes_supported':['c_lab_canary.read','offline_access']}
@app.get('/authorize')
def authorize(request:Request):
    if not READY:return error(503,'canary_not_configured')
    q=request.query_params
    if any(len(q.getlist(k))!=1 for k in q):return error(400,'invalid_request')
    scopes=q.get('scope','').split()
    if not scopes or len(scopes)!=len(set(scopes)) or set(scopes)-{'c_lab_canary.read','offline_access'}:return error(400,'invalid_scope')
    challenge=q.get('code_challenge','')
    if (q.get('client_id') not in CLIENTS or q.get('redirect_uri')!=CLIENTS.get(q.get('client_id')) or
        q.get('resource')!=ISSUER+'/mcp' or q.get('response_type')!='code' or
        q.get('code_challenge_method')!='S256' or re.fullmatch(r'[A-Za-z0-9_-]{43}',challenge) is None or
        'c_lab_canary.read' not in q.get('scope','').split() or
        not q.get('state') or len(q['state'])>512):
        return error(400,'invalid_request')
    if q['client_id']==OPENAI_CIMD:
        # Fetch only the exact hardcoded OpenAI metadata URL; never an arbitrary client-supplied URL.
        try:
            meta=httpx.get(OPENAI_CIMD,timeout=6,follow_redirects=False)
            meta.raise_for_status()
            doc=meta.json()
            if (doc.get('client_id')!=OPENAI_CIMD or CALLBACK not in doc.get('redirect_uris',[])
                or 'none' not in doc.get('token_endpoint_auth_methods_supported',[])):
                return error(400,'cimd_metadata_mismatch')
        except Exception:return error(503,'cimd_metadata_unavailable')
    state,nonce=fresh(),fresh()
    with Db.begin() as db:
        db.add(Intent(state_hash=hashed(state),nonce_hash=hashed(nonce),
                      client_state=q['state'],client=q['client_id'],redirect=q['redirect_uri'],challenge=challenge,
                      scope=q.get('scope',''),expires=clock()+300))
    params={'client_id':GOOGLE_ID,'redirect_uri':ISSUER+'/google/callback','response_type':'code',
            'scope':'openid email profile','nonce':nonce,'state':state,'prompt':'select_account'}
    return RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params),status_code=302)
@app.get('/google/callback')
async def google_callback(request:Request):
    if not READY:return error(503,'canary_not_configured')
    state,google_code=request.query_params.get('state',''),request.query_params.get('code','')
    if not state or not google_code:return error(400,'invalid_google_callback')
    with Db.begin() as db:
        row=db.execute(select(Intent).where(Intent.state_hash==hashed(state)).with_for_update()).scalar_one_or_none()
        if not row or row.used or row.expires<=clock():return error(400,'invalid_state')
        row.used=True
        nonce_hash,challenge,client_state,scope=row.nonce_hash,row.challenge,row.client_state,row.scope
        auth_client,auth_redirect=row.client,row.redirect
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response=await client.post('https://oauth2.googleapis.com/token',data={
                'code':google_code,'client_id':GOOGLE_ID,'client_secret':GOOGLE_SECRET,
                'redirect_uri':ISSUER+'/google/callback','grant_type':'authorization_code'})
            response.raise_for_status()
            signed=response.json()['id_token']
        key=jwt.PyJWKClient('https://www.googleapis.com/oauth2/v3/certs').get_signing_key_from_jwt(signed)
        identity=jwt.decode(signed,key.key,algorithms=['RS256'],audience=GOOGLE_ID,
                  issuer=['accounts.google.com','https://accounts.google.com'],leeway=30,
                  options={'require':['exp','iat','iss','aud','sub']})
    except Exception:
        return error(401,'invalid_google_identity')
    if (not identity.get('sub') or (identity.get('azp') and identity.get('azp')!=GOOGLE_ID) or identity.get('email_verified') is not True or
        str(identity.get('email','')).lower()!=ALLOWED_EMAIL or
        not hmac.compare_digest(hashed(str(identity.get('nonce',''))),nonce_hash)):
        return error(403,'identity_not_allowed')
    authorization_code=fresh()
    with Db.begin() as db:
        db.add(Code(code_hash=hashed(authorization_code),user_hash=hashed(identity['sub']),
                    challenge=challenge,client=auth_client,redirect=auth_redirect,scope=scope,expires=clock()+90))
    return RedirectResponse(auth_redirect+'?'+urlencode({'code':authorization_code,'state':client_state,'iss':ISSUER}),302)
def recovery_key():
    key=os.environ.get('CANARY_REFRESH_RECOVERY_KEY','')
    if len(key)<43:return None
    return hashlib.sha256(b'C-LAB-CANARY-RECOVERY-V1\0'+key.encode()).digest()

def retry_digest(old_hashed,attempt):
    return hashed('retry-attempt-v1:'+old_hashed+':'+attempt)

def decrypt_recovery(entry,old_hashed,attempt,client):
    aad=(old_hashed+'|'+entry.attempt_hash+'|'+client+'|'+ISSUER+'/mcp').encode()
    data=AESGCM(recovery_key()).decrypt(bytes.fromhex(entry.nonce),
                base64.b64decode(entry.encrypted_result),aad)
    return json.loads(data)

def create_recovery(db,row,old_hashed,attempt,client,response):
    digest=retry_digest(old_hashed,attempt)
    aad=(old_hashed+'|'+digest+'|'+client+'|'+ISSUER+'/mcp').encode()
    nonce=secrets.token_bytes(12)
    enc=AESGCM(recovery_key()).encrypt(nonce,json.dumps(response,separators=(',',':')).encode(),aad)
    db.add(RefreshRecovery(old_token_id=row.id,attempt_hash=digest,
               encrypted_result=base64.b64encode(enc).decode(),nonce=nonce.hex(),expires=clock()+120,
               successor_refresh_hash=hashed(response['refresh_token'])))

def suppress_one_committed_reply(db,fam,attempt):
    # No public arming endpoint. Exact private operator env + native session + short deadline.
    run=os.environ.get('CANARY_V8_FAULT_RUN','')
    target=os.environ.get('CANARY_V8_FAULT_SESSION','')
    try:until=int(os.environ.get('CANARY_V8_FAULT_UNTIL','0'))
    except ValueError:return False
    now=clock()
    if (fam.client!=OPENAI_CIMD or re.fullmatch(r'CLAB-V8-LOSS-[A-Za-z0-9_-]{8,100}',run) is None
        or re.fullmatch(r'[a-f0-9]{64}',target) is None or target!=session_ref(fam.id)
        or not now<until<=now+1800):return False
    consumed=db.execute(text('INSERT INTO canary_fault_once_v8 (run_id,session_ref,epoch,had_idempotency) '
        'VALUES (:run,:session,:epoch,:idem) ON CONFLICT (run_id) DO NOTHING RETURNING run_id'),
        {'run':run,'session':target,'epoch':now,'idem':attempt is not None}).scalar_one_or_none()
    if consumed is None:return False
    trace(db,'refresh_reply_suppressed',fam.id,client_auth='none')
    return True

def rotate_refresh(db,raw_refresh,client=CLIENT,attempt=None):
    count(db,'refresh_grant_received')
    row=db.execute(select(Token).where(Token.hashed==hashed(raw_refresh),
               Token.kind=='refresh').with_for_update()).scalar_one_or_none()
    if not row:return error(400,'invalid_grant')
    trace(db,'refresh_grant_received',row.family,row.hashed,row.expires)
    if attempt is not None:trace(db,'refresh_retry_bound',row.family,row.hashed,row.expires)
    fam=db.execute(select(Family).where(Family.id==row.family).with_for_update()).scalar_one()
    if fam.revoked or fam.client!=client or fam.resource!=ISSUER+'/mcp' or fam.policy_hash!=policy_binding(client) or 'offline_access' not in fam.scope.split() or row.expires<=clock():
        return error(400,'invalid_grant')
    old_hashed=row.hashed
    if row.consumed_at is not None:
        if attempt is not None:
            receipt=db.get(RefreshRecovery,row.id)
            if (receipt is not None and receipt.expires>=clock() and
                hmac.compare_digest(receipt.attempt_hash,retry_digest(old_hashed,attempt))):
                successor=db.execute(select(Token).where(Token.hashed==receipt.successor_refresh_hash,
                          Token.kind=='refresh')).scalar_one_or_none()
                if (successor is None or successor.family!=fam.id or
                        successor.consumed_at is not None or successor.expires<=clock()):
                    return error(400,'invalid_grant')
                try:return decrypt_recovery(receipt,old_hashed,attempt,client)
                except Exception:return error(503,'recovery_unavailable')
        if clock()-row.consumed_at>3:fam.revoked=True
        return error(400,'invalid_grant')
    row.consumed_at=clock()
    result=mint(db,fam.id,fam.scope)
    if attempt is not None:create_recovery(db,row,old_hashed,attempt,client,result)
    count(db,'refresh_success')
    trace(db,'refresh_success',fam.id,row.hashed,row.expires)
    if suppress_one_committed_reply(db,fam,attempt):result['__v8_drop_committed']=True
    return result

@app.post('/token')
async def token(request:Request):
    if not READY:return error(503,'canary_not_configured')
    if request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':
        return error(415,'invalid_request')
    body=await request.body()
    if len(body)>8192:return error(413,'invalid_request')
    try:parsed=parse_qs(body.decode('utf-8'),keep_blank_values=True,strict_parsing=True)
    except (ValueError,UnicodeError):return error(400,'invalid_request')
    if any(len(v)!=1 for v in parsed.values()):return error(400,'invalid_request')
    form={k:v[0] for k,v in parsed.items()}
    if form.get('client_id') not in CLIENTS or form.get('resource')!=ISSUER+'/mcp':
        return error(400,'invalid_client')
    # AS advertises only none: reject unexpected client authentication, never silently ignore assertions.
    if request.headers.get('authorization') or any(k in form for k in ('client_assertion','client_assertion_type','client_secret')):
        return error(400,'invalid_client')
    kind=form.get('grant_type')
    if kind=='authorization_code':
        verifier=form.get('code_verifier','')
        if not (re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier) is not None and form.get('redirect_uri')==CLIENTS[form['client_id']]):
            return error(400,'invalid_grant')
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        with Db.begin() as db:
            row=db.execute(select(Code).where(Code.code_hash==hashed(form.get('code',''))).with_for_update()).scalar_one_or_none()
            if not row or row.used or row.expires<=clock() or row.client!=form['client_id'] or row.redirect!=form['redirect_uri'] or not hmac.compare_digest(challenge,row.challenge):
                return error(400,'invalid_grant')
            row.used=True
            family=Family(user_hash=row.user_hash,client=row.client,resource=ISSUER+'/mcp',scope=row.scope,policy_hash=policy_binding(row.client))
            db.add(family);db.flush()
            result=mint(db,family.id,row.scope)
        return JSONResponse(result,headers={'Cache-Control':'no-store','Pragma':'no-cache'})
    if kind=='refresh_token':
        retry=request.headers.get('Idempotency-Key')
        if retry is not None and os.environ.get('CANARY_V6_RECOVERY_ENABLED')!='1':return error(503,'recovery_disabled')
        if retry is not None:
            if re.fullmatch(r'[A-Za-z0-9_-]{43,128}',retry) is None:
                return error(400,'invalid_idempotency_key')
            if recovery_key() is None:return error(503,'recovery_not_configured')
        with Db.begin() as db:
            result=rotate_refresh(db,form.get('refresh_token',''),form['client_id'],retry)
        if isinstance(result,Response):return result
        if result.pop('__v8_drop_committed',False):
            return JSONResponse({'error':'temporarily_unavailable','error_description':'Controlled one-time canary response loss after durable rotation'},status_code=503,headers={'Retry-After':'1','Cache-Control':'no-store'})
        return JSONResponse(result,headers={'Cache-Control':'no-store','Pragma':'no-cache'})
    return error(400,'unsupported_grant_type')
@app.post('/mcp')
async def mcp(request:Request):
    if not READY:return error(503,'canary_not_configured')
    try:req=await request.json()
    except Exception:return error(400,'invalid_json')
    if not isinstance(req,dict) or req.get('jsonrpc')!='2.0':return error(400,'invalid_json_rpc')
    method=req.get('method')
    # Public MCP discovery exposes only a synthetic tool, never user or science data.
    if method=='notifications/initialized':return Response(status_code=202)
    if method=='initialize':
        protocol=req.get('params',{}).get('protocolVersion','2025-03-26')
        if protocol not in ('2025-11-25','2025-06-18','2025-03-26','2024-11-05'):return error(400,'unsupported_protocol')
        result={'protocolVersion':protocol,'capabilities':{'tools':{}},
                'serverInfo':{'name':'C-Lab OAuth Canary','version':'0.2.0'}}
        return {'jsonrpc':'2.0','id':req.get('id'),'result':result}
    if method=='tools/list':
        result={'tools':[{'name':'canary_control_health',
                'description':'Synthetic read-only OAuth continuity probe; no production C-Lab access',
                'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
                'securitySchemes':[{'type':'oauth2','scopes':['c_lab_canary.read']}],
                'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}]}
        return {'jsonrpc':'2.0','id':req.get('id'),'result':result}
    if method!='tools/call' or not isinstance(req.get('params'),dict) or req['params'].get('name')!='canary_control_health':
        return {'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32601,'message':'Method not found'}}
    challenge='Bearer resource_metadata="'+ISSUER+'/.well-known/oauth-protected-resource/mcp", error="invalid_token", error_description="OAuth login required for the canary read tool"'
    def link_required():
        return {'jsonrpc':'2.0','id':req.get('id'),'result':{
          'content':[{'type':'text','text':'Authentication required'}],
          'isError':True,'_meta':{'mcp/www_authenticate':[challenge]}}}
    bearer=request.headers.get('authorization','')
    if not bearer.startswith('Bearer '):return link_required()
    with Db.begin() as db:
        item=db.execute(select(Token).where(Token.hashed==hashed(bearer[7:]),Token.kind=='access')).scalar_one_or_none()
        fam=db.get(Family,item.family) if item else None
        if item is not None and fam is not None and item.expires<=clock():
            trace(db,'access_expired',fam.id,item.hashed,item.expires,'bearer')
        if not item or item.expires<=clock() or not fam or fam.revoked or fam.resource!=ISSUER+'/mcp' or fam.client not in CLIENTS or fam.policy_hash!=policy_binding(fam.client) or 'c_lab_canary.read' not in fam.scope.split():
            return link_required()
        count(db,'access_validated')
        trace(db,'access_validated',fam.id,item.hashed,item.expires,'bearer')
        # Session-local, bearer-authorized aggregate: no token refs, secrets or other family events.
        own_session=session_ref(fam.id)
        session_counts=dict(db.execute(
            select(OAuthTrace.kind,func.count(OAuthTrace.seq))
            .where(OAuthTrace.session_ref==own_session).group_by(OAuthTrace.kind)).all())
        latest_refresh=db.execute(
            select(OAuthTrace.kind,OAuthTrace.epoch,OAuthTrace.client_auth)
            .where(OAuthTrace.session_ref==own_session,
                   OAuthTrace.kind.in_(('refresh_grant_received','refresh_success')))
            .order_by(OAuthTrace.seq.desc()).limit(8)).all()
        session_proof={
            'source':'postgresql_canary_oauth_trace_v8',
            'session_scoped':True,
            'refresh_grant_received':session_counts.get('refresh_grant_received',0),
            'refresh_success':session_counts.get('refresh_success',0),
            'refresh_token_issued':session_counts.get('refresh_token_issued',0),
            'access_validated':session_counts.get('access_validated',0),
            'recent_refresh_events':[{'kind':e.kind,'epoch':e.epoch,'client_auth':e.client_auth}
                                     for e in reversed(latest_refresh)]}
        observed={'audit_session':session_ref(fam.id),'oauth_client_id':fam.client,'resource':fam.resource,'scope':fam.scope,'server_epoch':clock(),'access_expires_at':item.expires,'access_issued_at':item.expires-90,'client_origin_proof':'PUBLIC_CLIENT_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED','session_oauth_audit':session_proof}
    result={'content':[{'type':'text','text':json.dumps(dict(component='C-Lab OAuth Canary',ok=True,science_access=False,**observed))}],'isError':False}
    return {'jsonrpc':'2.0','id':req.get('id'),'result':result}
@app.get('/internal/event-counts')
def events(request:Request):
    if Db is None:return error(503,'database_not_configured')
    admin=os.environ.get('METRICS_READ_TOKEN','')
    if len(admin)<32 or not hmac.compare_digest(admin,request.headers.get('x-canary-metrics-key','')):
        return error(403,'forbidden')
    with Db.begin() as db: values={x.name:x.total for x in db.scalars(select(Event))}
    return JSONResponse({'events':values,'database_backend':dbengine.dialect.name},headers={'Cache-Control':'no-store'})

# Fixed isolated PostgreSQL audit remains available while OAuth is disabled.
from .audit_routes import install as install_audit
import sys as _sys
install_audit(_sys.modules[__name__])

from .security_middleware import install as install_security
install_security(_sys.modules[__name__])