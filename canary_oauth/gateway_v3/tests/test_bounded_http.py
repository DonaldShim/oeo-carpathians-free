import subprocess,sys,time
import pytest
from gateway import bounded_http

def test_disallowed_destination_killed_without_credentials():
    with pytest.raises(bounded_http.BoundedHTTPError):
        bounded_http.request('GET','https://evil.invalid/',timeout=5)

def test_real_subprocess_deadline_reaps_stalled_worker(monkeypatch):
    real=subprocess.Popen;children=[]
    def stalled(*args,**kwargs):
        p=real([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
        children.append(p)
        return p
    monkeypatch.setattr(bounded_http.subprocess,'Popen',stalled)
    started=time.monotonic()
    with pytest.raises(bounded_http.BoundedHTTPError):
        bounded_http.request('POST','https://oauth2.googleapis.com/token',timeout=.3)
    assert time.monotonic()-started<3
    assert children[0].poll() is not None

def test_subprocess_args_never_contain_bearer(monkeypatch):
    observed=[]
    class Child:
        returncode=2
        def communicate(self,body,timeout):
            assert b'synthetic-private-bearer' in body
            return b'',None
    def fake(args,**kwargs):observed.append((args,kwargs));return Child()
    monkeypatch.setattr(bounded_http.subprocess,'Popen',fake)
    with pytest.raises(bounded_http.BoundedHTTPError):
        bounded_http.request('POST','https://oauth2.googleapis.com/token',headers={'Authorization':'Bearer synthetic-private-bearer'})
    assert 'synthetic-private-bearer' not in repr(observed)

def test_real_parent_response_supports_google_status_validation(monkeypatch):
    import base64,json
    class Child:
        returncode=0
        def communicate(self,body,timeout):
            return json.dumps({'status':200,'headers':{'content-type':'application/json'},
                'body':base64.b64encode(b'{"access_token":"synthetic","refresh_token":"synthetic","id_token":"synthetic","expires_in":3600}').decode()}).encode(),None
    monkeypatch.setattr(bounded_http.subprocess,'Popen',lambda *a,**k:Child())
    response=bounded_http.request('POST','https://oauth2.googleapis.com/token')
    response.raise_for_status()
    assert response.json()['expires_in']==3600
    from gateway.google import GoogleProvider
    from types import SimpleNamespace
    provider=GoogleProvider(SimpleNamespace(google_client_id='synthetic.apps.googleusercontent.com',
        google_client_secret='SYNTHETIC_NOT_A_SECRET',google_callback='https://fixture.invalid/callback'))
    assert provider.exchange('synthetic-code','synthetic-verifier')['expires_in']==3600
    assert provider.refresh('synthetic-refresh')['expires_in']==3600
