"""Canary-only fixed database audit, gated by the existing independent metrics key."""
import hashlib,hmac,json,os,pathlib,uuid
from urllib.parse import parse_qs
from fastapi import Request
from fastapi.responses import HTMLResponse,JSONResponse

def install(s):
 @s.app.get('/internal/security-replay')
 def form():
  return HTMLResponse('<!doctype html><title>C-Lab Canary database audit</title><h1>Isolated PostgreSQL security replay</h1><p>Trusted fixed audit only. No Google login or real token issuance. Random temporary schema is removed on completion.</p><form method="post"><label>Metrics key <input name="metrics_key" type="password" required maxlength="256" autocomplete="off"></label><button>Run fixed audit</button></form>',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; form-action 'self'; frame-ancestors 'none'",'Referrer-Policy':'no-referrer'})
 @s.app.post('/internal/security-replay')
 async def replay(request:Request):
  if s.READY:return s.error(409,'disable_oauth_before_audit')
  if request.headers.get('origin') not in (None,s.ISSUER):return s.error(403,'origin_denied')
  if request.headers.get('content-type','').split(';')[0]!='application/x-www-form-urlencoded':return s.error(415,'invalid_request')
  body=await request.body()
  if len(body)>1024:return s.error(413,'invalid_request')
  try:values=parse_qs(body.decode(),strict_parsing=True)
  except (ValueError,UnicodeError):return s.error(400,'invalid_request')
  expected=os.environ.get('METRICS_READ_TOKEN','');key=values.get('metrics_key',[''])[0]
  if set(values)!={'metrics_key'} or len(values['metrics_key'])!=1 or len(expected)<32 or not hmac.compare_digest(key,expected):return s.error(403,'forbidden')
  from .postgres_replay import run
  # Fixed function; no caller commands, SQL, URL, path, tokens, or user identifiers.
  import asyncio
  result=await asyncio.to_thread(run,s)
  result.update(run_id='CANARY-PG-'+uuid.uuid4().hex,source_sha256=hashlib.sha256(pathlib.Path(s.__file__).read_bytes()).hexdigest())
  return JSONResponse(result,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
