"""Secret-bearing requests use stdin/stdout pipes and a killable HTTP-only child.

No bearer or OAuth code is put in argv, environment, diagnostics or disk.
The parent enforces a wall-clock limit independent of socket/read timeouts.
"""
import json
import os
import signal
import subprocess
import sys
import time

class BoundedHTTPError(RuntimeError):
    pass

def request(method, url, *, headers=None, data=None, json_body=None, timeout=20):
    if not 0 < timeout <= 25:
        raise BoundedHTTPError('invalid total deadline')
    payload=json.dumps({'method':method,'url':url,'headers':headers or {},
                        'data':data,'json_body':json_body}).encode()
    if len(payload)>65536:raise BoundedHTTPError('request exceeds bound')
    started=time.monotonic()
    p=subprocess.Popen([sys.executable,'-m','gateway.http_worker'],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        start_new_session=(os.name!='nt'))
    try:
        raw,_=p.communicate(payload,timeout=max(.001,timeout-(time.monotonic()-started)))
    except (subprocess.TimeoutExpired,BaseException):
        if p.poll() is None:
            try:
                if os.name!='nt':os.killpg(p.pid,signal.SIGKILL)
                else:p.kill()
            except ProcessLookupError:pass
        p.communicate(timeout=2)
        raise BoundedHTTPError('provider request terminated') from None
    if p.returncode or len(raw)>400000:
        raise BoundedHTTPError('provider request failed')
    try:
        result=json.loads(raw)
        import httpx
        import base64
        return httpx.Response(result['status'],headers=result['headers'],
                              content=base64.b64decode(result['body'],validate=True),
                              request=httpx.Request(method,url))
    except Exception:
        raise BoundedHTTPError('invalid provider response') from None
