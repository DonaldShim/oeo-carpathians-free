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
