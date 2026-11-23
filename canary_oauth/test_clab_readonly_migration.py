"""Synthetic OAuth-scoped MCP migration tests, no Google OAuth or live GCP writes."""
import os,json,unittest,time,hashlib,base64
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from canary_oauth import canary_server as s

s.READY=True
s.ISSUER="https://c-lab-oauth-canary-20261025.onrender.com"
s.PEPPER="TEST_SYNTHETIC_ONLY_ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789"
s.ALLOWED_EMAIL="example@example.invalid"
s.GOOGLE_ID="SYNTHETIC_GOOGLE_ID"
s.GOOGLE_SECRET="SYNTHETIC_NOT_USABLE"
dbengine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
s.Base.metadata.create_all(dbengine)
s.Db=sessionmaker(bind=dbengine,expire_on_commit=False)
s.CLAB_TOKEN_FOR_TEST_ONLY="synthetic_token_never_live"
def issue(scope="c_lab_control.read offline_access",resource=None,expired=False,client=None):
    raw="local-"+str(time.time_ns())+"-test-only"
    client=client or s.CLIENT
    with s.Db.begin() as db:
        fam=s.Family(user_hash="LOCAL_TEST_ONLY",client=client,
                     resource=resource or s.ISSUER+"/mcp",
                     scope=scope,policy_hash=s.policy_binding(client),revoked=False)
        db.add(fam);db.flush()
        db.add(s.Token(hashed=s.hashed(raw),kind="access",family=fam.id,
                       expires=s.clock()-(30 if expired else -500)))
    return raw
def rpc(client,method,params=None,token=None):
    headers={"Authorization":"Bearer "+token} if token is not None else {}
    return client.post("/mcp",json={"jsonrpc":"2.0","id":23,"method":method,
                           "params":params or {}},headers=headers)

class FakeResponse:
    status_code=200
    def __init__(self,data):
        self._data=data
        self.content=json.dumps(data).encode()
    def json(self):return self._data
class FakeAsyncClient:
    next_result=None
    last_url=None
    last_headers=None
    def __init__(self,*a,**kw):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def post(self,url,json=None,headers=None):
        FakeAsyncClient.last_url=url
        FakeAsyncClient.last_headers=headers
        return FakeResponse(FakeAsyncClient.next_result)

class OAuthBridgeTests(unittest.TestCase):
 def setUp(self):
    self.c=TestClient(s.app)
    os.environ.pop("CLAB_READONLY_PROXY_TOKEN",None)
 def test_initialize(self):
    x=rpc(self.c,"initialize",{"protocolVersion":"2025-06-18"}).json()
    self.assertEqual(x["result"]["serverInfo"]["version"],"1.0.0")
 def test_tools_fixed_read_only(self):
    tools=rpc(self.c,"tools/list").json()["result"]["tools"]
    self.assertEqual({t["name"] for t in tools},{"get_control_health","get_controller_status","get_fabric_health","get_snapshot_provenance","get_guest_health"})
    self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
    self.assertTrue(all(t["securitySchemes"][0]["scopes"]==["c_lab_control.read"] for t in tools))
 def test_no_anonymous_read(self):
    x=rpc(self.c,"tools/call",{"name":"get_guest_health","arguments":{}}).json()
    self.assertTrue(x["result"]["isError"])
 def test_wrong_legacy_scope_cannot_escalate(self):
    x=rpc(self.c,"tools/call",{"name":"get_guest_health","arguments":{}},issue("c_lab_canary.read offline_access")).json()
    self.assertTrue(x["result"]["isError"])
 def test_unknown_science_tools_rejected(self):
    for name in ("compute_submit","compute_stage","start_vm","operator_run_worker_task","__proto__"):
        x=rpc(self.c,"tools/call",{"name":name},issue()).json()
        self.assertEqual(x["error"]["code"],-32601)
 def test_args_injection_rejected(self):
    x=rpc(self.c,"tools/call",{"name":"get_guest_health","arguments":{"command":"start_vm"}},issue()).json()
    self.assertEqual(x["error"]["code"],-32602)
 def test_missing_upstream_secret_is_fail_closed(self):
    x=rpc(self.c,"tools/call",{"name":"get_guest_health"},issue()).json()
    self.assertEqual(json.loads(x["result"]["content"][0]["text"])["availability"],"UNAVAILABLE_PROXY_CONFIGURATION")
 def test_resource_binding(self):
    x=rpc(self.c,"tools/call",{"name":"get_guest_health"},issue(resource="https://attacker.invalid/mcp")).json()
    self.assertTrue(x["result"]["isError"])
 def test_expired_token(self):
    x=rpc(self.c,"tools/call",{"name":"get_guest_health"},issue(expired=True)).json()
    self.assertTrue(x["result"]["isError"])
 def test_neon_failure_not_as_relogin(self):
    saved=s.Db
    try:
        s.Db=None
        x=rpc(self.c,"tools/call",{"name":"get_guest_health"},issue_token).json()
        body=json.loads(x["result"]["content"][0]["text"])
        self.assertEqual(body["availability"],"UNAVAILABLE_AUTH_STORAGE")
    finally:s.Db=saved
 def test_valid_fixed_upstream_and_provenance(self):
    token=issue()
    os.environ["CLAB_READONLY_PROXY_TOKEN"]="L"*64
    val={"schema":"CLAB_GUEST_HEALTH_READONLY_V1","fresh":True,"source":"c-lab-controller-01/systemd-http-readonly",
         "overall":"PASS","fabric_end_to_end":"NOT_TESTED","age_s":3}
    FakeAsyncClient.next_result={"jsonrpc":"2.0","id":12,"result":{"isError":False,
                               "content":[{"type":"text","text":json.dumps(val)}]}}
    with patch("canary_oauth.clab_readonly_route.httpx.AsyncClient",FakeAsyncClient):
        x=rpc(self.c,"tools/call",{"name":"get_guest_health"},token).json()
    self.assertFalse(x["result"]["isError"])
    self.assertEqual(FakeAsyncClient.last_url,"https://c-lab-archive-only-free-20261123.onrender.com/mcp")
 def test_stale_upstream_rejected(self):
    token=issue()
    os.environ["CLAB_READONLY_PROXY_TOKEN"]="L"*64
    val={"schema":"CLAB_GUEST_HEALTH_READONLY_V1","fresh":False,"source":"c-lab-controller-01/systemd-http-readonly",
         "overall":"PASS","fabric_end_to_end":"NOT_TESTED"}
    FakeAsyncClient.next_result={"jsonrpc":"2.0","id":12,"result":{"isError":False,
                               "content":[{"type":"text","text":json.dumps(val)}]}}
    with patch("canary_oauth.clab_readonly_route.httpx.AsyncClient",FakeAsyncClient):
        x=rpc(self.c,"tools/call",{"name":"get_guest_health"},token).json()
    self.assertTrue(x["result"]["isError"])
    self.assertEqual(json.loads(x["result"]["content"][0]["text"])["availability"],"UNAVAILABLE_STALE_SOURCE")
 def test_authorize_scope_new_not_old(self):
    challenge=base64.urlsafe_b64encode(hashlib.sha256(b"z"*45).digest()).decode().rstrip("=")
    params={"client_id":s.CLIENT,"redirect_uri":s.CALLBACK,"resource":s.ISSUER+"/mcp",
          "response_type":"code","code_challenge_method":"S256","code_challenge":challenge,
          "scope":"c_lab_control.read offline_access","state":"synthetic_state"}
    x=self.c.get("/authorize",params=params,follow_redirects=False)
    self.assertEqual(x.status_code,302)
    self.assertTrue(x.headers["location"].startswith("https://accounts.google.com/"))
    params["scope"]="compute_submit offline_access"
    y=self.c.get("/authorize",params=params,follow_redirects=False)
    self.assertEqual(y.status_code,400)
 def test_protected_resource_metadata(self):
    x=self.c.get("/.well-known/oauth-protected-resource/mcp").json()
    self.assertIn("c_lab_control.read",x["scopes_supported"])

issue_token=issue()
if __name__=="__main__":unittest.main(verbosity=2)
