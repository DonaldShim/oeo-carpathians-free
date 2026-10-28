from __future__ import annotations
import httpx
import json,time
from fastapi import HTTPException
from .config import Settings,GOOGLE_TOKEN_URL,GOOGLE_IDENTITY_ISSUERS
from .bounded_http import request, BoundedHTTPError

class GoogleProvider:
    def __init__(self,settings:Settings):
        self.settings=settings
    def exchange(self,code:str,verifier:str):
        try:
            response=request('POST',GOOGLE_TOKEN_URL,data={
            'code':code,'client_id':self.settings.google_client_id,
            'client_secret':self.settings.google_client_secret,
            'redirect_uri':self.settings.google_callback,
            'code_verifier':verifier,'grant_type':'authorization_code'})
            print(json.dumps({'event':'google_exchange_http','status':response.status_code,'epoch':int(time.time())}),flush=True)
            response.raise_for_status()
            result=response.json()
        except (httpx.HTTPError,ValueError,BoundedHTTPError):
            raise HTTPException(status_code=502,detail="Google token endpoint failed")
        if not result.get('id_token') or not result.get('access_token') or not result.get('refresh_token'):
            raise HTTPException(status_code=403,detail='Google did not issue required offline credentials')
        return result
    def verify(self,token:str,nonce:str):
        from google.oauth2 import id_token
        class CertificateRequest:
            def __call__(self,url,method='GET',**kwargs):
                r=request(method,url)
                return type('CertificateResponse',(),{'status':r.status_code,'data':r.content})()
        try:
            claims=id_token.verify_oauth2_token(token, CertificateRequest(), self.settings.google_client_id)
        except Exception:
            raise HTTPException(status_code=403,detail="invalid Google identity token")
        if claims.get('iss') not in GOOGLE_IDENTITY_ISSUERS or claims.get('nonce')!=nonce:
            raise HTTPException(status_code=403,detail='invalid Google identity token')
        if claims.get('azp',self.settings.google_client_id)!=self.settings.google_client_id:
            raise HTTPException(status_code=403,detail='invalid Google authorized party')
        if claims.get('email_verified') not in (True,'true'):
            raise HTTPException(status_code=403,detail='email not verified')
        if claims.get('email','').casefold()!=self.settings.allowed_google_email.casefold():
            raise HTTPException(status_code=403,detail='user not admitted')
        if not claims.get('sub'):
            raise HTTPException(status_code=403,detail='Google subject missing')
        return claims
    def refresh(self,refresh_token:str):
        try:
            response=request('POST',GOOGLE_TOKEN_URL,data={'refresh_token':refresh_token,
                'client_id':self.settings.google_client_id,'client_secret':self.settings.google_client_secret,
                'grant_type':'refresh_token'})
            print(json.dumps({'event':'google_refresh_http','status':response.status_code,'epoch':int(time.time())}),flush=True)
            response.raise_for_status()
            result=response.json()
        except (httpx.HTTPError,ValueError,BoundedHTTPError):
            raise HTTPException(status_code=502,detail="Google token endpoint failed")
        if not result.get('access_token') or not 0<int(result.get('expires_in',0))<=86400:
            raise HTTPException(status_code=503,detail='Google refresh did not issue access token')
        return result
