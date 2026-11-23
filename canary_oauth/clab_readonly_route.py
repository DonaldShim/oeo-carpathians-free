"""Scope-bound C-Lab read-only MCP bridge to existing Render V2.2.
No arbitrary upstream URLs, methods, parameters or scientific execution.
"""
import os,json,hmac
import httpx
from fastapi import Request,Response

READ_SCOPE="c_lab_control.read"
UPSTREAM="https://c-lab-archive-only-free-20261123.onrender.com/mcp"
OPS=("get_control_health","get_controller_status","get_fabric_health",
     "get_snapshot_provenance","get_guest_health")
INPUT={"type":"object","properties":{},"additionalProperties":False}

def install(s):
    app=s.app
    def rpc(id, result):
        return {"jsonrpc":"2.0","id":id,"result":result}
    def err(id,code,name):
        return {"jsonrpc":"2.0","id":id,"error":{"code":code,"message":name}}
    def auth_required(id):
        challenge='Bearer resource_metadata="'+s.ISSUER+'/.well-known/oauth-protected-resource/mcp", error="invalid_token"'
        return rpc(id,{"content":[{"type":"text","text":"OAuth authorization required"}],
                   "isError":True,"_meta":{"mcp/www_authenticate":[challenge]}})
    def unavailable(id,name,reason):
        return rpc(id,{"content":[{"type":"text","text":json.dumps({
             "method":name,"fresh":False,"availability":reason,
             "source":"Render V2.2 scoped read-only",
             "fabric_end_to_end":"NOT_TESTED","science_executed":False
         },sort_keys=True)}],"isError":True})
    def authorized(bearer):
        if not bearer.startswith("Bearer ") or len(bearer)>1024:return False
        try:
            with s.Db.begin() as db:
                tok=db.execute(s.select(s.Token).where(
                    s.Token.hashed==s.hashed(bearer[7:]),
                    s.Token.kind=="access")).scalar_one_or_none()
                family=db.get(s.Family,tok.family) if tok else None
                valid=bool(tok and tok.expires>s.clock() and family and not family.revoked and
                    family.resource==s.ISSUER+"/mcp" and family.client in s.CLIENTS and
                    hmac.compare_digest(family.policy_hash,s.policy_binding(family.client)) and
                    READ_SCOPE in family.scope.split())
                if valid:
                    s.count(db,"access_validated")
                    s.trace(db,"access_validated",family.id,tok.hashed,tok.expires,"bearer")
                return valid
        except Exception:
            return False
    async def upstream(id,name):
        key=os.environ.get("CLAB_READONLY_PROXY_TOKEN","")
        if len(key)<48 or len(key)>512 or key!=key.strip():
            return unavailable(id,name,"UNAVAILABLE_PROXY_CONFIGURATION")
        payload={"jsonrpc":"2.0","id":12,"method":"tools/call",
                 "params":{"name":name,"arguments":{}}}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(58.0,connect=8.0),
                                         follow_redirects=False,trust_env=False) as client:
                resp=await client.post(UPSTREAM,json=payload,headers={
                    "Authorization":"Bearer "+key,"Content-Type":"application/json",
                    "Cache-Control":"no-store"})
            if resp.status_code!=200 or len(resp.content)>24000:
                return unavailable(id,name,"UNAVAILABLE_SOURCE_HTTP")
            data=resp.json()
            if not isinstance(data,dict) or data.get("jsonrpc")!="2.0" or data.get("id")!=12 or "error" in data:
                return unavailable(id,name,"UNAVAILABLE_SOURCE_CONTRACT")
            result=data.get("result") or {}
            items=result.get("content") or []
            if result.get("isError") or len(items)!=1 or items[0].get("type")!="text":
                return unavailable(id,name,"UNAVAILABLE_SOURCE_CONTRACT")
            value=json.loads(items[0].get("text",""))
            if not isinstance(value,dict) or value.get("fresh") is not True:
                return unavailable(id,name,"UNAVAILABLE_STALE_SOURCE")
            if name=="get_guest_health":
                if value.get("schema")!="CLAB_GUEST_HEALTH_READONLY_V1" or \
                   value.get("source")!="c-lab-controller-01/systemd-http-readonly" or \
                   value.get("fabric_end_to_end")!="NOT_TESTED":
                    return unavailable(id,name,"UNAVAILABLE_SOURCE_PROVENANCE")
            elif value.get("schema")!="CLAB_READONLY_GCP_CONTROLPLANE_SNAPSHOT_V2" or \
                 value.get("method")!=name or value.get("compute_executed") is not False:
                return unavailable(id,name,"UNAVAILABLE_SOURCE_PROVENANCE")
            return rpc(id,{"content":[{"type":"text", "text":json.dumps(value,sort_keys=True)}],
                           "isError":False})
        except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError):
            return unavailable(id,name,"UNAVAILABLE_SOURCE_NETWORK")
    @app.post("/mcp")
    async def mcp(request:Request):
        if not s.READY:return s.error(503,"oauth_not_configured")
        cl=request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl)>8192 or int(cl)<0:return s.error(413,"invalid_length")
            except ValueError:return s.error(400,"invalid_length")
        raw=await request.body()
        if len(raw)>8192:return s.error(413,"invalid_length")
        try:data=json.loads(raw)
        except (ValueError,TypeError):return s.error(400,"invalid_json")
        if not isinstance(data,dict) or data.get("jsonrpc")!="2.0":
            return s.error(400,"invalid_json_rpc")
        mid=data.get("id");method=data.get("method")
        if method=="notifications/initialized":return Response(status_code=202)
        if method=="initialize":
            params=data.get("params") or {}
            if not isinstance(params,dict):return err(mid,-32602,"INVALID_PARAMS")
            version=params.get("protocolVersion","2025-06-18")
            if version not in ("2025-11-25","2025-06-18","2025-03-26"):
                return err(mid,-32602,"UNSUPPORTED_PROTOCOL")
            return rpc(mid,{"protocolVersion":version,
                    "capabilities":{"tools":{"listChanged":False}},
                    "serverInfo":{"name":"C-Lab Render Free OAuth Read-only","version":"1.0.0"}})
        if method=="ping":return rpc(mid,{})
        if method=="tools/list":
            return rpc(mid,{"tools":[{
                "name":name,
                "description":"Authenticated C-Lab V2.2 snapshot; NOT an execution tool.",
                "inputSchema":INPUT,
                "securitySchemes":[{"type":"oauth2","scopes":[READ_SCOPE]}],
                "annotations":{"readOnlyHint":True,"destructiveHint":False,
                               "idempotentHint":True,"openWorldHint":False}
                } for name in OPS]})
        if method!="tools/call":return err(mid,-32601,"METHOD_NOT_FOUND")
        params=data.get("params")
        if not isinstance(params,dict):return err(mid,-32602,"INVALID_PARAMS")
        name=params.get("name")
        if name not in OPS:return err(mid,-32601,"TOOL_NOT_ALLOWED")
        if params.get("arguments",{}) not in ({},None):
            return err(mid,-32602,"NO_ARGUMENTS_ALLOWED")
        if not authorized(request.headers.get("authorization","")):
            return auth_required(mid)
        return await upstream(mid,name)
