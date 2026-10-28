"""C-Lab OAuth gateway using atomic Firestore state. No PostgreSQL, no Drive transactions.

Google Drive is a user-accessible encrypted backup destination, NEVER the live
source of truth for code/refresh rotation. Do not route production until actual
Google and ChatGPT OAuth acceptance have been observed.
"""
from __future__ import annotations
import json, re, secrets, time
from typing import Any
from urllib.parse import urlencode
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from .config import Settings, GOOGLE_AUTH_URL, READ_TOOLS
from .crypto import Cipher, digest, random_token, challenge_from_verifier, valid_verifier
from .google import GoogleProvider
from .upstream import Upstream, TOOL_META
from .firestore_store import FirestoreOAuthStore, GrantFailure

PKCE_RE=re.compile(r'^[A-Za-z0-9_-]{43}$')


def create_app(settings: Settings, store=None, provider=None, upstream=None) -> FastAPI:
    if settings.storage_backend != 'firestore':
        raise ValueError('Firestore app requires FIRESTORE_BACKEND=firestore')
    app=FastAPI(title='C-Lab OAuth Gateway Firestore',docs_url=None,openapi_url=None,redoc_url=None)
    store=store or FirestoreOAuthStore(settings.firestore_project_id,prefix=settings.firestore_prefix)
    google=provider or GoogleProvider(settings)
    upstream=upstream or Upstream(settings)
    cipher=Cipher(settings.gateway_encryption_key)
    def now():return int(time.time())
    def fail(status=400, detail='invalid_request'):raise HTTPException(status_code=status,detail=detail)
    def tokens(access, refresh):
        return JSONResponse({'access_token':access,'refresh_token':refresh,'token_type':'Bearer',
                             'expires_in':settings.access_lifetime_seconds,'scope':'clab.read'},
                            headers={'Cache-Control':'no-store','Pragma':'no-cache'})

    @app.middleware('http')
    async def private(request:Request,call_next):
        if request.url.path in ('/authorize','/google/callback'):
            keys=list(request.query_params.keys())
            if any(len(request.query_params.getlist(k))!=1 for k in keys):
                return JSONResponse({'error':'duplicate_parameter'},status_code=400)
        if request.url.path in ('/token','/revoke'):
            raw=await request.body()
            if len(raw)>8192:return JSONResponse({'error':'request_too_large'},status_code=413)
            if request.headers.get('authorization'):
                return JSONResponse({'error':'unsupported_client_authentication'},status_code=400)
        try:
            response=await call_next(request)
        except Exception:
            return JSONResponse({'error':'dependency_unavailable'},status_code=503,
                                headers={'Cache-Control':'no-store'})
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        return response

    @app.get('/health')
    def health():
        ready=False
        try:ready=store.health()
        except Exception:pass
        return {'component':'c-lab-oauth-gateway-firestore','ready':ready,
                'mode':'read-only','resource':settings.resource,
                'google_oauth_configured':bool(settings.google_client_id and settings.google_client_secret),
                'google_authorization_verified':False}

    @app.get('/.well-known/oauth-protected-resource')
    def protected_resource():
        return {'resource':settings.resource,'authorization_servers':[settings.public_base_url],
                'resource_name':'C-Lab Read-only OAuth Gateway',
                'scopes_supported':['clab.read'],'bearer_methods_supported':['header']}

    @app.get('/.well-known/oauth-authorization-server')
    def issuer():
        base=settings.public_base_url
        return {'issuer':base,'authorization_endpoint':base+'/authorize',
                'token_endpoint':base+'/token','revocation_endpoint':base+'/revoke',
                'client_id_metadata_document_supported':True,
                'authorization_response_iss_parameter_supported':True,
                'token_endpoint_auth_methods_supported':['none'],
                'response_types_supported':['code'],
                'grant_types_supported':['authorization_code','refresh_token'],
                'code_challenge_methods_supported':['S256'],'scopes_supported':['clab.read']}

    @app.get('/authorize')
    def authorize(request:Request,response_type:str='',client_id:str='',redirect_uri:str='',state:str='',
                  code_challenge:str='',code_challenge_method:str='',scope:str='clab.read',resource:str=''):
        if (response_type!='code' or client_id!=settings.client_id or
            redirect_uri not in settings.allowed_redirect_uris or not state or len(state)>1024 or
            resource!=settings.resource or scope.strip()!='clab.read' or
            code_challenge_method!='S256' or not PKCE_RE.fullmatch(code_challenge)):
            fail(400,'invalid OAuth client request')
        epoch=now(); g_state=random_token(); verifier=secrets.token_urlsafe(64); nonce=random_token()
        payload={'state':state,'client_id':client_id,'redirect_uri':redirect_uri,
                 'challenge':code_challenge,'resource':resource,'nonce':nonce,
                 'google_verifier':verifier}
        try:
            store.admit_rate(digest(request.client.host if request.client else 'unknown'),epoch)
            store.create_flow(digest(g_state),cipher.encrypt(json.dumps(payload)),epoch+600,epoch)
        except GrantFailure:
            fail(429,'authorization admission denied')
        params={'response_type':'code','client_id':settings.google_client_id,
                'redirect_uri':settings.google_callback,'scope':'openid email profile',
                'state':g_state,'access_type':'offline',
                'code_challenge':challenge_from_verifier(verifier),
                'code_challenge_method':'S256','nonce':nonce}
        if settings.google_prompt_consent:params['prompt']='consent'
        return RedirectResponse(GOOGLE_AUTH_URL+'?'+urlencode(params),status_code=302)

    @app.get('/google/callback')
    def google_callback(state:str='',code:str='',error:str=''):
        if not state or len(state)>1024:fail(400,'invalid callback state')
        try:payload=json.loads(cipher.decrypt(store.take_flow(digest(state),now())))
        except GrantFailure:fail(400,'state invalid or already used')
        if error or not code:
            params={'error':'access_denied' if error else 'server_error',
                    'state':payload['state'],'iss':settings.public_base_url}
            return RedirectResponse(payload['redirect_uri']+'?'+urlencode(params),status_code=302)
        result=google.exchange(code,payload['google_verifier'])
        claims=google.verify(result['id_token'],payload['nonce'])
        if not result.get('refresh_token') or not result.get('access_token') or not 0<int(result.get('expires_in',0))<=86400:
            fail(403,'Google offline authorization incomplete')
        gid=random_token(); local_code=random_token();t=now()
        store.issue_code(gid,claims['sub'],cipher.encrypt(claims['email']),
                         cipher.encrypt(result['refresh_token']),cipher.encrypt(result['access_token']),
                         t+int(result['expires_in']),payload['resource'],payload['client_id'],
                         digest(local_code),payload['challenge'],payload['redirect_uri'],t+300,t)
        return RedirectResponse(payload['redirect_uri']+'?'+urlencode({
            'code':local_code,'state':payload['state'],'iss':settings.public_base_url}),status_code=302)

    @app.post('/token')
    async def token(request:Request):
        if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/x-www-form-urlencoded':
            fail(415,'form encoding required')
        form=await request.form()
        if any(len(form.getlist(k))!=1 for k in form) or any(k in form for k in ('client_secret','client_assertion','client_assertion_type')):
            fail(400,'duplicate_parameter_or_unsupported_client_authentication')
        client_id=str(form.get('client_id',''));resource=str(form.get('resource',''))
        if client_id!=settings.client_id or resource!=settings.resource:
            fail(400,'invalid_client_or_resource')
        grant_type=str(form.get('grant_type',''));t=now()
        try:
            if grant_type=='authorization_code':
                verifier=str(form.get('code_verifier',''))
                if not valid_verifier(verifier):fail(400,'invalid_pkce_verifier')
                return tokens(*store.redeem_code(digest(str(form.get('code',''))),
                        challenge_from_verifier(verifier),str(form.get('redirect_uri','')),
                        client_id,resource,t,settings.access_lifetime_seconds,settings.refresh_lifetime_seconds))
            if grant_type=='refresh_token':
                raw=str(form.get('refresh_token',''))
                if not raw or len(raw)>300:fail(400,'invalid_grant')
                return tokens(*store.rotate_refresh(digest(raw),client_id,resource,t,
                    settings.access_lifetime_seconds,settings.refresh_lifetime_seconds))
        except GrantFailure:fail(400,'invalid_grant')
        fail(400,'unsupported_grant_type')

    @app.post('/revoke')
    async def revoke(request:Request):
        if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/x-www-form-urlencoded':
            fail(415,'form encoding required')
        form=await request.form()
        if any(len(form.getlist(k))!=1 for k in form) or any(k in form for k in ('client_secret','client_assertion','client_assertion_type')):
            fail(400,'duplicate_parameter_or_unsupported_client_authentication')
        if str(form.get('client_id',''))!=settings.client_id:fail(400,'invalid_client')
        raw=str(form.get('token',''))
        if len(raw)>300:fail(400,'invalid_request')
        store.revoke(digest(raw),settings.client_id)
        return Response(status_code=200)

    @app.api_route('/mcp',methods=['GET','POST'])
    async def mcp(request:Request):
        challenge=(f'Bearer resource_metadata="{settings.public_base_url}/.well-known/oauth-protected-resource", '
                   'scope="clab.read", error="invalid_token"')
        header=request.headers.get('authorization','')
        try:
            if not header.startswith('Bearer ') or len(header)>350:raise GrantFailure('invalid_token')
            grant=store.get_grant_from_access(digest(header[7:]),settings.resource,now())
        except GrantFailure:
            return JSONResponse({'error':'invalid_token','_meta':{'mcp/www_authenticate':[challenge]}},
                                status_code=401,headers={'WWW-Authenticate':challenge})
        if request.method=='GET':return Response(status_code=405,headers={'Allow':'POST'})
        if int(request.headers.get('content-length','0') or '0')>65536:fail(413,'request too large')
        raw=await request.body()
        if len(raw)>65536:fail(413,'request too large')
        try:body=json.loads(raw)
        except ValueError:fail(400,'invalid JSON')
        if not isinstance(body,dict) or body.get('jsonrpc')!='2.0':fail(400,'invalid json-rpc request')
        method=body.get('method');reqid=body.get('id')
        def ret(data:Any):return {'jsonrpc':'2.0','id':reqid,'result':data}
        if method=='notifications/initialized':return Response(status_code=202)
        if method=='initialize':
            return JSONResponse(ret({'protocolVersion':'2025-06-18',
               'capabilities':{'tools':{'listChanged':False}},
               'serverInfo':{'name':'c-lab-oauth-firestore-gateway','version':'2.0'}}))
        if method=='ping':return JSONResponse(ret({}))
        if method=='tools/list':
            return JSONResponse(ret({'tools':[
                {'name':n,'description':TOOL_META[n],
                 'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
                 'securitySchemes':[{'type':'oauth2','scopes':['clab.read']}],
                 'annotations':{'readOnlyHint':True,'destructiveHint':False}}
                for n in sorted(READ_TOOLS)]}))
        if method=='tools/call':
            args=body.get('params',{})
            if not isinstance(args,dict) or args.get('name') not in READ_TOOLS or args.get('arguments',{})!={}: 
                return JSONResponse({'jsonrpc':'2.0','id':reqid,
                    'error':{'code':-32602,'message':'Unadmitted tool or arguments'}})
            try:access=store.google_access(grant,cipher,google,now())
            except GrantFailure:fail(503,'upstream refresh not available')
            return JSONResponse(ret(upstream.invoke(args['name'],access)))
        return JSONResponse({'jsonrpc':'2.0','id':reqid,'error':{'code':-32601,'message':'Method not found'}})
    return app

# Fail closed: production app requires all real OAuth secrets and Firestore settings.
import os
app = create_app(Settings.from_env()) if os.getenv('GATEWAY_STORAGE_BACKEND') == 'firestore' else None
