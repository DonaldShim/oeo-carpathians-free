"""Cloud Run startup stays observable and denies OAuth while secrets are missing."""
import os
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from .config import Settings

def configured_app():
    try:
        settings=Settings.from_env()
        from .firestore_app import create_app
        return create_app(settings)
    except (ValueError,KeyError):
        app=FastAPI(docs_url=None,openapi_url=None,redoc_url=None)
        @app.get('/health')
        def health():
            db=False
            try:
                from .firestore_store import FirestoreOAuthStore
                db=FirestoreOAuthStore(os.environ['FIRESTORE_PROJECT_ID'],
                    prefix=os.environ.get('FIRESTORE_PREFIX','clab_gateway_v3')).health()
            except Exception:pass
            return JSONResponse({'component':'c-lab-oauth-gateway-v3','ready':False,
                'firestore_reachable':db,'google_oauth_configured':False,
                'reason':'CONFIGURATION_INCOMPLETE'},status_code=503,
                headers={'Cache-Control':'no-store'})
        @app.api_route('/{path:path}',methods=['GET','POST','PUT','DELETE','PATCH'])
        def denied(path:str):
            return JSONResponse({'error':'temporarily_unavailable'},status_code=503,
                                headers={'Cache-Control':'no-store'})
        return app

app=configured_app()
