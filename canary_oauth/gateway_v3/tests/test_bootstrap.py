import importlib
from fastapi.testclient import TestClient

def test_missing_secret_never_ready_or_authorizes(monkeypatch):
    monkeypatch.delenv('GOOGLE_CLIENT_SECRET',raising=False)
    monkeypatch.setenv('FIRESTORE_PROJECT_ID','synthetic-test')
    monkeypatch.setenv('GATEWAY_STORAGE_BACKEND','firestore')
    import gateway.firestore_store
    class Store:
        def __init__(self,*a,**k):pass
        def health(self):return True
    monkeypatch.setattr(gateway.firestore_store,'FirestoreOAuthStore',Store)
    import gateway.bootstrap
    app=gateway.bootstrap.configured_app()
    with TestClient(app) as c:
        response=c.get('/health')
        assert response.status_code==503
        assert response.json()['ready'] is False
        assert response.json()['firestore_reachable'] is True
        assert response.json()['google_oauth_configured'] is False
        assert c.get('/authorize').status_code==503
        assert c.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code==503
