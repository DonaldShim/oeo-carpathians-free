"""Bounded forms and shared PostgreSQL rate limits. No bearer/callback logging."""
from sqlalchemy import text
from starlette.responses import JSONResponse
import time
def install(s):
 @s.app.middleware('http')
 async def security(request,call_next):
  if request.method=='POST':
   chunks=[];size=0
   async for chunk in request.stream():
    size+=len(chunk)
    if size>8192:return s.error(413,'invalid_request')
    chunks.append(chunk)
   request._body=b''.join(chunks)
  if s.Db is not None and request.url.path in ('/authorize','/google/callback','/token'):
   minute=int(time.time())//60
   key=s.hashed(str(request.client.host if request.client else 'unknown')+'|'+request.url.path+'|'+str(minute))
   try:
    with s.Db.begin() as db:
     total=db.execute(text('INSERT INTO canary_rate_limit(key,total,expires) VALUES (:k,1,:e) ON CONFLICT (key) DO UPDATE SET total=canary_rate_limit.total+1 RETURNING total'),{'k':key,'e':(minute+2)*60}).scalar()
     if total==1:db.execute(text('DELETE FROM canary_rate_limit WHERE expires<:t'),{'t':int(time.time())})
    if total>60:return s.error(429,'rate_limited')
   except Exception:return s.error(503,'database_unavailable')
  try:response=await call_next(request)
  except Exception:return s.error(503,'service_unavailable')
  response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer';response.headers['X-Content-Type-Options']='nosniff'
  return response
