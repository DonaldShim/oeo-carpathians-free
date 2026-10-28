from __future__ import annotations
import json, re, secrets, time
from urllib.parse import urlencode
from typing import Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import select, update, func
from .config import Settings, GOOGLE_AUTH_URL, READ_TOOLS
from .crypto import Cipher, digest, random_token, challenge_from_verifier, valid_verifier
from .db import Base, Flow, Grant, AuthCode, AccessToken, RefreshToken, record, build_engine
from .google import GoogleProvider
from .upstream import Upstream, TOOL_META

PKCE_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')


def create_app(settings:Settings, provider:GoogleProvider|None=None, upstream:Upstream|None=None,
               create_schema:bool=False) -> FastAPI:
    app=FastAPI(title='C-Lab OAuth Gateway',docs_url=None,redoc_url=None,openapi_url=None)
    engine=build_engine(settings.database_url)
    if create_schema:
        Base.metadata.create_all(engine)
    cipher=Cipher(settings.gateway_encryption_key)
    google=provider or GoogleProvider(settings)
    upstream_adapter=upstream or Upstream(settings)
    app.state.engine=engine
    app.state.settings=settings

    def now():return int(time.time())
    def fail(status:int=400, detail:str='invalid_request'):
        raise HTTPException(status_code=status,detail=detail)
    def new_access(s:Session,grant_id:str,t:int):
        token=random_token()
        s.add(AccessToken(token_hash=digest(token),grant_id=grant_id,
                          expires=t+settings.access_lifetime_seconds,revoked=False))
        return token
    def new_refresh(s:Session,grant_id:str,family:str,t:int):
        token=random_token()
        s.add(RefreshToken(token_hash=digest(token),grant_id=grant_id,family=family,
                           expires=t+settings.refresh_lifetime_seconds,consumed=False))
        return token
    def token_response(access:str,refresh:str):
        return JSONResponse({'access_token':access,'refresh_token':refresh,'token_type':'Bearer',
             'expires_in':settings.access_lifetime_seconds,'scope':'clab.read'},headers={'Cache-Control':'no-store','Pragma':'no-cache'})

    @app.middleware('http')
    async def no_store_and_transport(request:Request,call_next):
        # No forwarding or serving sensitive data via shared intermediary caches.
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        return response

    @app.get('/health')
    def health():
        from sqlalchemy import text
        operational=False
        try:
            with Session(engine) as session:
                session.execute(text('SELECT 1 FROM grants LIMIT 1'))
            operational=True
        except Exception:
            operational=False
        return {'component':'c-lab-google-offline-gateway','ready':operational,
                'mode':'read-only','resource':settings.resource,
                'google_oauth_configured':True,'google_authorization_verified':False,
                'test_or_prod':'dev' if settings.allow_sqlite_dev else 'gated'}

    @app.get('/.well-known/oauth-protected-resource')
    def protected_meta():
        return {'resource':settings.resource,'authorization_servers':[settings.public_base_url],
                'resource_name':'C-Lab Read-only OAuth Gateway','scopes_supported':['clab.read'],
                'bearer_methods_supported':['header']}

    @app.get('/.well-known/oauth-authorization-server')
    def auth_meta():
        b=settings.public_base_url
        return {'issuer':b,'authorization_endpoint':b+'/authorize',
             'token_endpoint':b+'/token',
             'revocation_endpoint':b+'/revoke',
             'authorization_response_iss_parameter_supported':True,
             'client_id_metadata_document_supported':True,
             'token_endpoint_auth_methods_supported':['none'],
             'response_types_supported':['code'],
             'grant_types_supported':['authorization_code','refresh_token'],
             'code_challenge_methods_supported':['S256'],
             'scopes_supported':['clab.read']}

    @app.get('/authorize')
    def authorize(response_type:str='',client_id:str='',redirect_uri:str='',state:str='',
                  code_challenge:str='',code_challenge_method:str='',scope:str='clab.read',
                  resource:str=''):
        if (response_type!='code' or client_id!=settings.client_id or
            redirect_uri not in settings.allowed_redirect_uris or not state or len(state)>1024 or
            resource != settings.resource or scope.strip()!='clab.read' or
            code_challenge_method!='S256' or not PKCE_RE.fullmatch(code_challenge)):
            fail(400,'invalid OAuth client request')
        google_state=random_token()
        google_verifier=secrets.token_urlsafe(64)
        nonce=random_token()
        payload={'state':state,'client_id':client_id,'redirect_uri':redirect_uri,
                 'challenge':code_challenge,'resource':resource,'nonce':nonce,
                 'google_verifier':google_verifier}
        with Session(engine) as s, s.begin():
            live=s.execute(select(func.count(Flow.state_hash)).where(Flow.expires > now(), Flow.consumed == False)).scalar_one()
            if live >= 200:
                fail(429,'authorization capacity exhausted')
            s.add(Flow(state_hash=digest(google_state),payload_cipher=cipher.encrypt(json.dumps(payload)),
                       expires=now()+600,consumed=False))
            record(s,now(),'google_authorize_start')
        params={'response_type':'code','client_id':settings.google_client_id,
                'redirect_uri':settings.google_callback,
                'scope':'openid email profile','state':google_state,'access_type':'offline',
                'code_challenge':challenge_from_verifier(google_verifier),
                'code_challenge_method':'S256','nonce':nonce}
        if settings.google_prompt_consent:
            params['prompt']='consent'
        return RedirectResponse(GOOGLE_AUTH_URL+'?'+urlencode(params),status_code=302)

    @app.get('/google/callback')
    def google_callback(state:str='',code:str='',error:str=''):
        if not state or len(state)>1024:
            fail(400,'invalid Google callback state')
        with Session(engine) as s, s.begin():
            row=s.execute(select(Flow).where(Flow.state_hash==digest(state)).with_for_update()).scalar_one_or_none()
            if not row or row.consumed or row.expires<=now():fail(400,'Google state invalid or used')
            row.consumed=True
            payload=json.loads(cipher.decrypt(row.payload_cipher))
        if error or not code:
            params={'error':'access_denied' if error else 'server_error',
                    'state':payload['state'],'iss':settings.public_base_url}
            return RedirectResponse(payload['redirect_uri']+'?'+urlencode(params),status_code=302)
        # Exchanges and verifies the REAL Google OIDC token; never trusts supplied email headers.
        issued=google.exchange(code,payload['google_verifier'])
        claims=google.verify(issued['id_token'],payload['nonce'])
        if (issued.get('expires_in',0)<=0 or not issued.get('refresh_token')
                or not issued.get('access_token') or not issued.get('id_token')):
            fail(403,'Google did not issue required offline credentials')
        grant_id=random_token()
        auth_code=random_token()
        with Session(engine) as s,s.begin():
            s.add(Grant(id=grant_id,google_sub=claims['sub'],
                email_cipher=cipher.encrypt(claims['email']),
                google_refresh_cipher=cipher.encrypt(issued['refresh_token']),
                google_access_cipher=cipher.encrypt(issued['access_token']),
                google_access_expires=now()+int(issued['expires_in']),
                resource=payload['resource'],client_id=payload['client_id'],
                scopes='clab.read',revoked=False))
            s.add(AuthCode(code_hash=digest(auth_code),grant_id=grant_id,
                challenge=payload['challenge'],redirect_uri=payload['redirect_uri'],
                expires=now()+300,consumed=False))
            record(s,now(),'google_offline_credential_issued',grant_id,'refresh_present')
        return RedirectResponse(payload['redirect_uri']+'?'+urlencode({
            'code':auth_code,'state':payload['state'],'iss':settings.public_base_url}),status_code=302)

    @app.post('/token')
    async def token(request:Request):
        if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/x-www-form-urlencoded':
            fail(415,'form encoding required')
        form=await request.form()
        grant_type=str(form.get('grant_type',''))
        client_id=str(form.get('client_id',''))
        resource=str(form.get('resource',''))
        if client_id!=settings.client_id or resource!=settings.resource:
            fail(400,'invalid_client_or_resource')
        t=now()
        if grant_type=='authorization_code':
            verifier=str(form.get('code_verifier',''))
            if not valid_verifier(verifier):fail(400,'invalid_pkce_verifier')
            with Session(engine) as s,s.begin():
                row=s.execute(select(AuthCode).where(AuthCode.code_hash==digest(str(form.get('code','')))).with_for_update()).scalar_one_or_none()
                if (not row or row.consumed or row.expires<=t or
                    row.redirect_uri!=str(form.get('redirect_uri','')) or
                    not secrets.compare_digest(row.challenge,challenge_from_verifier(verifier))):
                    fail(400,'invalid_grant')
                grant=s.get(Grant,row.grant_id)
                if not grant or grant.revoked or grant.client_id!=client_id or grant.resource!=resource:
                    fail(400,'invalid_grant')
                row.consumed=True
                access=new_access(s,grant.id,t)
                refresh=new_refresh(s,grant.id,random_token(),t)
                record(s,t,'gateway_access_and_refresh_issued',grant.id)
            return token_response(access,refresh)
        if grant_type=='refresh_token':
            raw=str(form.get('refresh_token',''))
            if len(raw)>300:fail(400,'invalid_grant')
            with Session(engine) as s,s.begin():
                row=s.execute(select(RefreshToken).where(RefreshToken.token_hash==digest(raw)).with_for_update()).scalar_one_or_none()
                if not row:fail(400,'invalid_grant')
                grant=s.execute(select(Grant).where(Grant.id==row.grant_id).with_for_update()).scalar_one_or_none()
                if not grant or grant.client_id!=client_id or grant.resource!=resource or grant.revoked:
                    fail(400,'invalid_grant')
                if row.consumed:
                    grant.revoked=True
                    s.execute(update(AccessToken).where(AccessToken.grant_id==grant.id).values(revoked=True))
                    record(s,t,'refresh_replay_grant_revoked',grant.id)
                    # Commit the revocation, then return the error outside the transaction.
                    outcome=None
                elif row.expires<=t:
                    fail(400,'invalid_grant')
                else:
                    row.consumed=True
                    access=new_access(s,grant.id,t)
                    refresh=new_refresh(s,grant.id,row.family,t)
                    record(s,t,'gateway_refresh_success',grant.id)
                    outcome=(access,refresh)
            if outcome is None:fail(400,'invalid_grant_refresh_replay')
            return token_response(*outcome)
        fail(400,'unsupported_grant_type')

    @app.post('/revoke')
    async def revoke(request:Request):
        if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/x-www-form-urlencoded':
            fail(415,'form encoding required')
        form=await request.form()
        if str(form.get('client_id',''))!=settings.client_id:
            fail(400,'invalid_client')
        raw=str(form.get('token',''))
        if len(raw)>300:
            fail(400,'invalid_request')
        h=digest(raw)
        with Session(engine) as s,s.begin():
            refresh=s.execute(select(RefreshToken).where(RefreshToken.token_hash==h).with_for_update()).scalar_one_or_none()
            access=s.execute(select(AccessToken).where(AccessToken.token_hash==h).with_for_update()).scalar_one_or_none()
            grant_id=refresh.grant_id if refresh else (access.grant_id if access else None)
            if grant_id:
                grant=s.execute(select(Grant).where(Grant.id==grant_id).with_for_update()).scalar_one_or_none()
                if grant and grant.client_id==settings.client_id:
                    grant.revoked=True
                    s.execute(update(AccessToken).where(AccessToken.grant_id==grant_id).values(revoked=True))
                    record(s,now(),'gateway_grant_revoked',grant_id)
        return Response(status_code=200,headers={'Cache-Control':'no-store'})

    def authorize_bearer(request:Request):
        header=request.headers.get('authorization','')
        if not header.startswith('Bearer ') or len(header)>350:
            fail(401,'invalid_token')
        bearer=header[7:]
        with Session(engine) as s:
            row=s.get(AccessToken,digest(bearer))
            if not row or row.revoked or row.expires<=now():fail(401,'invalid_token')
            grant=s.get(Grant,row.grant_id)
            if not grant or grant.revoked or grant.resource!=settings.resource or grant.scopes!='clab.read':
                fail(401,'invalid_token')
            return grant.id

    def google_access_for_grant(grant_id:str):
        with Session(engine) as s,s.begin():
            grant=s.execute(select(Grant).where(Grant.id==grant_id).with_for_update()).scalar_one_or_none()
            if not grant or grant.revoked:fail(401,'invalid_token')
            if grant.google_access_cipher and grant.google_access_expires>now()+30:
                return cipher.decrypt(grant.google_access_cipher)
            result=google.refresh(cipher.decrypt(grant.google_refresh_cipher))
            grant.google_access_cipher=cipher.encrypt(result['access_token'])
            grant.google_access_expires=now()+int(result.get('expires_in',3600))
            if result.get('refresh_token'):
                grant.google_refresh_cipher=cipher.encrypt(result['refresh_token'])
            record(s,now(),'google_refresh_success',grant.id)
            return result['access_token']

    @app.api_route('/mcp',methods=['GET','POST'])
    async def mcp(request:Request):
        try:grant_id=authorize_bearer(request)
        except HTTPException:
            # Advertise both HTTP challenge (server-level discovery) and MCP tool-level
            # www_authenticate metadata. Neither route invokes upstream without a bearer.
            challenge=(f'Bearer resource_metadata="{settings.public_base_url}/.well-known/oauth-protected-resource", '
                       'scope="clab.read", error="invalid_token", '
                       'error_description="Valid OAuth access token required"')
            return JSONResponse({'error':'invalid_token',
                '_meta':{'mcp/www_authenticate':[challenge]}},
                status_code=401,headers={'WWW-Authenticate':challenge})
        if request.method=='GET':
            return Response(status_code=405,headers={'Allow':'POST'})
        if int(request.headers.get('content-length','0') or '0') > 65536:
            fail(413,'request too large')
        raw_body=await request.body()
        if len(raw_body)>65536:
            fail(413,'request too large')
        try: body=json.loads(raw_body)
        except ValueError:fail(400,'invalid JSON')
        if not isinstance(body,dict) or body.get('jsonrpc')!='2.0':fail(400,'invalid json-rpc request')
        method=body.get('method')
        reqid=body.get('id')
        if method=='notifications/initialized':return Response(status_code=202)
        def result(value:Any):return {'jsonrpc':'2.0','id':reqid,'result':value}
        if method=='initialize':
            return JSONResponse(result({'protocolVersion':'2025-06-18',
                'capabilities':{'tools':{'listChanged':False}},
                'serverInfo':{'name':'c-lab-oauth-read-only-gateway','version':'1.0.0'}}))
        if method=='ping':return JSONResponse(result({}))
        if method=='tools/list':
            return JSONResponse(result({'tools':[
                {'name':n,'description':TOOL_META[n],
                 'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
                 'annotations':{'readOnlyHint':True,'destructiveHint':False},
                 '_meta':{'securitySchemes':[{'type':'oauth2','scopes':['clab.read']}]}}
                for n in sorted(READ_TOOLS)]}))
        if method=='tools/call':
            args=body.get('params',{})
            if not isinstance(args,dict) or args.get('name') not in READ_TOOLS or args.get('arguments',{}) != {}:
                return JSONResponse({'jsonrpc':'2.0','id':reqid,'error':{'code':-32602,'message':'Unadmitted tool or arguments'}})
            google_access=google_access_for_grant(grant_id)
            # Fixed destination, strict allowlist, exactly one read-only upstream call.
            return JSONResponse(result(upstream_adapter.invoke(args['name'],google_access)))
        return JSONResponse({'jsonrpc':'2.0','id':reqid,'error':{'code':-32601,'message':'Method not found'}})
    return app

# Production starts fail-closed when mandatory config or durable DB is missing.
# Schema migrations are controlled separately; NEVER auto-create production tables.
app = None
try:
    app = create_app(Settings.from_env(),create_schema=False)
except (ValueError,KeyError):
    # A nonconfigured container fails immediately on startup. No synthetic auth fallback.
    if __name__ != '__main__':
        raise
