"""Internal fixed-destination network child. Never log exception or request data."""
import base64
import json
import sys
import httpx

ALLOWED={
    ('POST','https://oauth2.googleapis.com/token'),
    ('GET','https://www.googleapis.com/oauth2/v1/certs'),
    ('POST','https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp'),
}

def main():
    raw=sys.stdin.buffer.read(65537)
    if len(raw)>65536:return 2
    q=json.loads(raw)
    if (q['method'],q['url']) not in ALLOWED:return 2
    with httpx.Client(timeout=5,follow_redirects=False,trust_env=False) as c:
        with c.stream(q['method'],q['url'],headers=q['headers'],data=q['data'],json=q['json_body']) as r:
            body=bytearray()
            for block in r.iter_bytes():
                body.extend(block)
                if len(body)>262144:return 3
            headers={k:v for k,v in r.headers.items() if k in ('content-type','mcp-session-id')}
            sys.stdout.write(json.dumps({'status':r.status_code,'headers':headers,
                'body':base64.b64encode(body).decode('ascii')}))
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception:sys.exit(2)
