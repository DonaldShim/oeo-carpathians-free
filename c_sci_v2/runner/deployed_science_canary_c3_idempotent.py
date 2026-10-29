import urllib.error

def _safe_upload(req,name,expected):
 try:
  return json.loads(urllib.request.urlopen(req,timeout=25).read())
 except urllib.error.HTTPError as exc:
  if exc.code != 412: raise
  path=urllib.parse.quote(name,safe="")
  geturl="https://storage.googleapis.com/storage/v1/b/"+B+"/o/"+path+"?alt=media"
  request=urllib.request.Request(geturl,headers={"Authorization":"Bearer "+token()})
  existing=urllib.request.urlopen(request,timeout=25).read()
  if existing != expected: raise ValueError("IMMUTABLE_COLLISION")
  return {"generation":"REPLAY_IDENTICAL"}

import hashlib,json,urllib.request,urllib.parse,os
B="c-sci-clean-v1-855271818322"
I="c-sci-col10000-20261029-c3"
N=10000
def data(x):return (json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode()
def token():
 req=urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",headers={"Metadata-Flavor":"Google"})
 return json.loads(urllib.request.urlopen(req,timeout=10).read())["access_token"]
def send(name,body):
 path=urllib.parse.quote(name,safe="")
 url="https://storage.googleapis.com/upload/storage/v1/b/"+B+"/o?uploadType=media&name="+path+"&ifGenerationMatch=0"
 req=urllib.request.Request(url,data=body,headers={"Authorization":"Bearer "+token(),"Content-Type":"application/json"},method="POST")
 return _safe_upload(req,name,body)
steps=[]
for seed in range(1,N+1):
 n=seed;s=0
 while n!=1:
  n=(3*n+1 if n%2 else n//2);s+=1
 steps.append(s)
m=max(steps)
result={"schema":"C_SCI_SCIENTIFIC_RESULT_V1","case":"COLLATZ_FINITE_CANARY","limit":N,"certified_scope":"integer seeds from 1 to "+str(N)+"; finite only","all_reached_one":True,"maximum_stopping_time":m,"argmax":steps.index(m)+1,"sum_stopping_times":sum(steps),"trace_sha256":hashlib.sha256(",".join(map(str,steps)).encode()).hexdigest(),"global_collatz_theorem_proved":False}
b=data(result)
out=send("runs/"+I+"/SCIENTIFIC_RESULT.json",b)
print("C_SCI_RESULT_UPLOADED=true,sha256="+hashlib.sha256(b).hexdigest()+",generation="+str(out["generation"]))
import hashlib,json,urllib.request,urllib.parse
B="c-sci-clean-v1-855271818322";I="c-sci-col10000-20261029-c3";N=10000
def data(x):return (json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode()
def token():
 req=urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",headers={"Metadata-Flavor":"Google"})
 return json.loads(urllib.request.urlopen(req,timeout=10).read())["access_token"]
def read(name):
 u="https://storage.googleapis.com/storage/v1/b/"+B+"/o/"+urllib.parse.quote(name,safe="")+"?alt=media"
 return urllib.request.urlopen(urllib.request.Request(u,headers={"Authorization":"Bearer "+token()}),timeout=25).read()
def upload(name,raw):
 u="https://storage.googleapis.com/upload/storage/v1/b/"+B+"/o?uploadType=media&name="+urllib.parse.quote(name,safe="")+"&ifGenerationMatch=0"
 req=urllib.request.Request(u,data=raw,headers={"Authorization":"Bearer "+token(),"Content-Type":"application/json"},method="POST")
 return _safe_upload(req,name,raw)
raw=read("runs/"+I+"/SCIENTIFIC_RESULT.json")
r=json.loads(raw)
assert r["schema"]=="C_SCI_SCIENTIFIC_RESULT_V1" and r["limit"]==N and r["global_collatz_theorem_proved"] is False
counts=[]
for x in range(1,N+1):
 k=0
 while x!=1:
  x=x//2 if x%2==0 else 3*x+1
  k+=1
 counts.append(k)
assert r["sum_stopping_times"]==sum(counts) and r["maximum_stopping_time"]==max(counts)
assert r["argmax"]==counts.index(max(counts))+1
assert r["trace_sha256"]==hashlib.sha256(",".join(str(k) for k in counts).encode()).hexdigest()
assert raw==data(r)
receipt={"schema":"C_SCI_TERMINAL_RECEIPT_V1","invocation_id":I,"primary_artifact":"SCIENTIFIC_RESULT.json","primary_sha256":hashlib.sha256(raw).hexdigest(),"primary_size":len(raw),"execution_status":"FINISHED","scientific_status":"FINITE_CANARY_PASS","receipt_is_terminal":True,"independent_recompute":True}
obj=upload("runs/"+I+"/receipt.json",data(receipt))
print("C_SCI_RECEIPT_UPLOADED=true,sha256="+hashlib.sha256(data(receipt)).hexdigest()+",generation="+str(obj["generation"]))