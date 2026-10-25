"""Isolated C-Lab OAuth Canary. No C-Fabric tools, fail closed by default."""
import os, time, hmac, hashlib, base64, secrets, json
from urllib.parse import urlencode, parse_qs
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, select, text
from sqlalchemy.orm import declarative_base, sessionmaker
import jwt, httpx

Base=declarative_base()
class Intent(Base):
    __tablename__='canary_auth_intent'
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
    revoked=Column(Boolean,default=False,nullable=False)
class Token(Base):
    __tablename__='canary_token'
    id=Column(Integer,primary_key=True)
    hashed=Column(String(64),unique=True,nullable=False)
    kind=Column(String(16),nullable=False)
    family=Column(Integer,ForeignKey('canary_family.id'),nullable=False)
    expires=Column(Integer,nullable=False)
    consumed_at=Column(Integer,nullable=True)
class Event(Base):
    __tablename__='canary_event'
    name=Column(String(64),primary_key=True)
    total=Column(Integer,default=0,nullable=False)

ISSUER=os.environ.get('CANARY_ISSUER','').rstrip('/')
CLIENT='clab-canary-chatgpt-20261025'
CALLBACK='https://chatgpt.com/connector_platform_oauth_redirect'
GOOGLE_ID=os.environ.get('GOOGLE_OAUTH_CLIENT_ID','')
GOOGLE_SECRET=os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET','')
ALLOWED_EMAIL=os.environ.get('GOOGLE_ALLOWED_EMAIL','').lower().strip()
DATABASE_URL=os.environ.get('DATABASE_URL','')
PEPPER=os.environ.get('TOKEN_HASH_PEPPER','')
READY=(os.environ.get('CANARY_OAUTH_ENABLED')=='1' and ISSUER.startswith('https://') and
       GOOGLE_ID and GOOGLE_SECRET and ALLOWED_EMAIL and len(PEPPER)>=32 and
       DATABASE_URL.startswith(('postgres://','postgresql://','postgresql+psycopg://')))
dbengine=create_engine(("postgresql+psycopg://"+DATABASE_URL.split("://",1)[1] if DATABASE_URL.startswith(('postgres://','postgresql://')) else DATABASE_URL),pool_pre_ping=True) if READY else None
Db=sessionmaker(bind=dbengine) if READY else None
app=FastAPI(title='C-Lab OAuth Canary',docs_url=None,redoc_url=None,openapi_url=None)

@app.on_event('startup')
def prepare():
    if READY: Base.metadata.create_all(dbengine)
def clock():return int(time.time())
def fresh():return secrets.token_urlsafe(40)
def hashed(value):return hmac.new(PEPPER.encode(),value.encode(),hashlib.sha256).hexdigest()
def error(code,name):return JSONResponse({'error':name},status_code=code,headers={'Cache-Control':'no-store'})
def count(db,name):
    assert name in ('refresh_token_issued','refresh_grant_received','refresh_success','access_validated')
    db.execute(text('INSERT INTO canary_event(name,total) VALUES (:n,1) ON CONFLICT (name) DO UPDATE SET total=canary_event.total+1'),{'n':name})
def mint(db,fid):
    at,rt=fresh(),fresh()
    db.add(Token(hashed=hashed(at),kind='access',family=fid,expires=clock()+90))
    db.add(Token(hashed=hashed(rt),kind='refresh',family=fid,expires=clock()+86400))
    count(db,'refresh_token_issued')
    return {'access_token':at,'refresh_token':rt,'token_type':'Bearer','expires_in':90,'scope':'c_lab_canary.read offline_access'}
@app.get('/healthz')
def health():return {'service':'c-lab-oauth-canary','ready':bool(READY),'science_access':False}
@app.get('/.well-known/oauth-authorization-server')
def metadata():
    return {'issuer':ISSUER or 'https://disabled.invalid','authorization_endpoint':ISSUER+'/authorize',
      'token_endpoint':ISSUER+'/token','grant_types_supported':['authorization_code','refresh_token'],
      'response_types_supported':['code'],'code_challenge_methods_supported':['S256'],
      'authorization_response_iss_parameter_supported':True,
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
    challenge=q.get('code_challenge','')
    if (q.get('client_id')!=CLIENT or q.get('redirect_uri')!=CALLBACK or
        q.get('resource')!=ISSUER+'/mcp' or q.get('response_type')!='code' or
        q.get('code_challenge_method')!='S256' or len(challenge)!=43 or
        'c_lab_canary.read' not in q.get('scope','').split() or
        not q.get('state') or len(q['state'])>512):
        return error(400,'invalid_request')
    state,nonce=fresh(),fresh()
    with Db.begin() as db:
        db.add(Intent(state_hash=hashed(state),nonce_hash=hashed(nonce),
                      client_state=q['state'],challenge=challenge,
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
                    challenge=challenge,scope=scope,expires=clock()+90))
    return RedirectResponse(CALLBACK+'?'+urlencode({'code':authorization_code,'state':client_state,'iss':ISSUER}),302)
@app.post('/token')
async def token(request:Request):
    if not READY:return error(503,'canary_not_configured')
    if request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':
        return error(415,'invalid_request')
    body=await request.body()
    if len(body)>8192:return error(413,'invalid_request')
    form={k:v[0] for k,v in parse_qs(body.decode('utf-8'),keep_blank_values=True).items()}
    if form.get('client_id')!=CLIENT or form.get('resource')!=ISSUER+'/mcp':
        return error(400,'invalid_client')
    kind=form.get('grant_type')
    if kind=='authorization_code':
        verifier=form.get('code_verifier','')
        if not (43<=len(verifier)<=128 and form.get('redirect_uri')==CALLBACK):
            return error(400,'invalid_grant')
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        with Db.begin() as db:
            row=db.execute(select(Code).where(Code.code_hash==hashed(form.get('code',''))).with_for_update()).scalar_one_or_none()
            if not row or row.used or row.expires<=clock() or not hmac.compare_digest(challenge,row.challenge):
                return error(400,'invalid_grant')
            row.used=True
            family=Family(user_hash=row.user_hash,client=CLIENT,resource=ISSUER+'/mcp')
            db.add(family);db.flush()
            result=mint(db,family.id)
        return JSONResponse(result,headers={'Cache-Control':'no-store','Pragma':'no-cache'})
    if kind=='refresh_token':
        with Db.begin() as db:
            count(db,'refresh_grant_received')
            row=db.execute(select(Token).where(Token.hashed==hashed(form.get('refresh_token','')),
                       Token.kind=='refresh').with_for_update()).scalar_one_or_none()
            if not row:return error(400,'invalid_grant')
            fam=db.execute(select(Family).where(Family.id==row.family).with_for_update()).scalar_one()
            if fam.revoked or fam.client!=CLIENT or fam.resource!=ISSUER+'/mcp' or row.expires<=clock():
                return error(400,'invalid_grant')
            if row.consumed_at is not None:
                if clock()-row.consumed_at>3:fam.revoked=True
                return error(400,'invalid_grant')
            row.consumed_at=clock()
            result=mint(db,fam.id)
            count(db,'refresh_success')
        return JSONResponse(result,headers={'Cache-Control':'no-store','Pragma':'no-cache'})
    return error(400,'unsupported_grant_type')
@app.post('/mcp')
async def mcp(request:Request):
    if not READY:return error(503,'canary_not_configured')
    bearer=request.headers.get('authorization','')
    if not bearer.startswith('Bearer '):
        return JSONResponse({'error':'unauthorized'},status_code=401,headers={'WWW-Authenticate':
          'Bearer resource_metadata="'+ISSUER+'/.well-known/oauth-protected-resource/mcp"'})
    with Db.begin() as db:
        item=db.execute(select(Token).where(Token.hashed==hashed(bearer[7:]),Token.kind=='access')).scalar_one_or_none()
        fam=db.get(Family,item.family) if item else None
        if not item or item.expires<=clock() or not fam or fam.revoked or fam.resource!=ISSUER+'/mcp':
            return error(401,'unauthorized')
        count(db,'access_validated')
    try:req=await request.json()
    except Exception:return error(400,'invalid_json')
    if not isinstance(req,dict) or req.get('jsonrpc')!='2.0':return error(400,'invalid_json_rpc')
    method=req.get('method')
    if method=='notifications/initialized':return Response(status_code=202)
    if method=='initialize':
        result={'protocolVersion':'2025-11-25','capabilities':{'tools':{}},
                'serverInfo':{'name':'C-Lab OAuth Canary','version':'0.1.0'}}
    elif method=='tools/list':
        result={'tools':[{'name':'canary_control_health','description':'Synthetic OAuth continuity probe; no science access',
               'inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]}
    elif method=='tools/call' and req.get('params',{}).get('name')=='canary_control_health':
        result={'content':[{'type':'text','text':json.dumps({'component':'C-Lab OAuth Canary','ok':True,'science_access':False})}],'isError':False}
    else:
        return {'jsonrpc':'2.0','id':req.get('id'),'error':{'code':-32601,'message':'Method not found'}}
    return {'jsonrpc':'2.0','id':req.get('id'),'result':result}
@app.get('/internal/event-counts')
def events(request:Request):
    if not READY:return error(503,'canary_not_configured')
    admin=os.environ.get('METRICS_READ_TOKEN','')
    if len(admin)<32 or not hmac.compare_digest(admin,request.headers.get('x-canary-metrics-key','')):
        return error(403,'forbidden')
    with Db.begin() as db: values={x.name:x.total for x in db.scalars(select(Event))}
    return JSONResponse({'events':values},headers={'Cache-Control':'no-store'})
