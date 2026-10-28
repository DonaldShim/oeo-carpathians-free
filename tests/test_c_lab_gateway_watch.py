import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ops"))
import c_lab_gateway_watch as w

class GatewayWatchTests(unittest.TestCase):
    def setUp(self):
        self.responses={
          w.BASE+"/health":{"ready":True,"google_oauth_configured":True,"mode":"read-only","resource":w.BASE+"/mcp"},
          w.BASE+"/.well-known/oauth-protected-resource":{"resource":w.BASE+"/mcp","authorization_servers":[w.BASE],"scopes_supported":["clab.read"]},
          w.BASE+"/.well-known/oauth-authorization-server":{"issuer":w.BASE,"token_endpoint":w.BASE+"/token","authorization_endpoint":w.BASE+"/authorize","code_challenge_methods_supported":["S256"]},
          w.BASE+"/mcp":{}
        }
    def run_probe(self):
        with patch.object(w,"fetch_json",side_effect=lambda u,s:self.responses[u]):
            return w.probe()
    def test_all_green(self):self.assertEqual(self.run_probe(),[])
    def test_health_false_rejected(self):
        self.responses[w.BASE+"/health"]["ready"]=False
        self.assertIn("health:ValueError",self.run_probe())
    def test_wrong_issuer_rejected(self):
        self.responses[w.BASE+"/.well-known/oauth-authorization-server"]["issuer"]="https://invalid.example"
        self.assertIn("authorization_server:ValueError",self.run_probe())
    def test_wrong_anonymous_mcp_rejected(self):
        with patch.object(w,"fetch_json",side_effect=lambda u,s: (_ for _ in ()).throw(ValueError()) if u.endswith("/mcp") else self.responses[u]):
            self.assertIn("anonymous_mcp:ValueError",w.probe())
    def test_no_issue_without_secret(self):
        with patch.dict(os.environ,{"GITHUB_TOKEN":"","GITHUB_REPOSITORY":""}):
            self.assertIsNone(w.reconcile_issue(["health:ValueError"]))
    def test_single_issue_creation(self):
        calls=[]
        def fake(method,path,body=None):
            calls.append((method,path))
            if method=="GET":return []
        with patch.dict(os.environ,{"GITHUB_TOKEN":"test","GITHUB_REPOSITORY":"example/repo"}):
            with patch.object(w,"github_api",side_effect=fake):
                w.reconcile_issue(["health:ValueError"])
        self.assertEqual(calls.count(("POST","issues")),1)
    def test_recovery_closes_issue(self):
        calls=[]
        def fake(method,path,body=None):
            calls.append((method,path))
            if method=="GET":return [{"number":11,"title":w.ISSUE_TITLE,"state":"open"}]
        with patch.dict(os.environ,{"GITHUB_TOKEN":"test","GITHUB_REPOSITORY":"example/repo"}):
            with patch.object(w,"github_api",side_effect=fake):
                w.reconcile_issue([])
        self.assertIn(("PATCH","issues/11"),calls)

if __name__=="__main__":unittest.main()
