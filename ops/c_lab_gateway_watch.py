#!/usr/bin/env python3
"""Credential-free public-health monitor; does not perform OAuth or change C-Lab."""
from __future__ import annotations
import json, os, sys, time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "https://c-lab-oauth-gateway-v3-855271818322.europe-west1.run.app"
ISSUE_TITLE = "[C-Lab Gateway V3] Public health regression"

def fetch_json(url, expected=200):
    request=Request(url,headers={"User-Agent":"C-Lab-Gateway-Watch/1.0","Accept":"application/json"},method="GET")
    try:
        with urlopen(request,timeout=12) as res:
            status,data=res.status,res.read(32769)
    except HTTPError as exc:
        status,data=exc.code,exc.read(32769)
    if status!=expected or len(data)>32768:
        raise ValueError("Wrong HTTP status or oversized response")
    if expected==401:return {}
    obj=json.loads(data)
    if not isinstance(obj,dict):raise ValueError("Non-object JSON")
    return obj

def probe():
    checks=[
        ("health","/health",200,lambda x: x.get("ready") is True and x.get("google_oauth_configured") is True
         and x.get("mode")=="read-only" and x.get("resource")==BASE+"/mcp"),
        ("protected_resource","/.well-known/oauth-protected-resource",200,
         lambda x: x.get("resource")==BASE+"/mcp" and BASE in x.get("authorization_servers",[])
         and "clab.read" in x.get("scopes_supported",[])),
        ("authorization_server","/.well-known/oauth-authorization-server",200,
         lambda x: x.get("issuer")==BASE and x.get("token_endpoint")==BASE+"/token"
         and x.get("authorization_endpoint")==BASE+"/authorize" and "S256" in x.get("code_challenge_methods_supported",[])),
        ("anonymous_mcp","/mcp",401,lambda x:True)
    ]
    failures=[]
    for name,path,expected,validate in checks:
        try:
            if not validate(fetch_json(BASE+path,expected)):
                raise ValueError("Bad readiness or metadata")
        except Exception as exc:
            failures.append(name+":"+type(exc).__name__)
    return failures

def github_api(method,path,body=None):
    token=os.environ.get("GITHUB_TOKEN","")
    repository=os.environ.get("GITHUB_REPOSITORY","")
    if not token or not repository or "/" not in repository:return None
    data=None if body is None else json.dumps(body).encode()
    req=Request("https://api.github.com/repos/"+repository+"/"+path,data=data,method=method,
       headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
                "X-GitHub-Api-Version":"2022-11-28",
                "User-Agent":"C-Lab-Gateway-Watch/1.0","Content-Type":"application/json"})
    with urlopen(req,timeout=15) as res:
        raw=res.read(262145)
        if len(raw)>262144:raise ValueError("GitHub response too large")
        return json.loads(raw) if raw else None

def reconcile_issue(failures):
    if not os.environ.get("GITHUB_TOKEN") or not os.environ.get("GITHUB_REPOSITORY"):return
    rows=github_api("GET","issues?state=all&per_page=100") or []
    matches=[x for x in rows if x.get("title")==ISSUE_TITLE and "pull_request" not in x]
    current=next((x for x in sorted(matches,key=lambda x:x.get("number",0),reverse=True)
                  if x.get("state")=="open"),None)
    if failures and not current:
        body=("Credential-free public-health check detected a problem.\n"
              "This monitor does NOT modify canonical production or OAuth sessions.\n\n"
              "Checks: "+", ".join(sorted(set(failures)))+
              "\n\nInvestigate V3 Cloud Run and Firestore; do not deploy or reconnect based on this alert alone.")
        github_api("POST","issues",{"title":ISSUE_TITLE,"body":body})
    if not failures and current:
        github_api("POST","issues/"+str(current["number"])+"/comments",
                   {"body":"Public-health probe recovered. This does not certify OAuth refresh."})
        github_api("PATCH","issues/"+str(current["number"]),{"state":"closed"})

def main():
    failures=[]
    for attempt in range(3):
        failures=probe()
        if not failures:break
        if attempt<2:time.sleep(4)
    try:
        reconcile_issue(failures)
    except Exception as exc:
        print("Alert delivery unconfirmed: "+type(exc).__name__,file=sys.stderr)
        if failures:failures.append("alert_delivery")
    if failures:
        print("GATEWAY_V3_WATCH_FAILURE="+",".join(sorted(set(failures))),file=sys.stderr)
        return 1
    print("GATEWAY_V3_PUBLIC_HEALTH_OK; no OAuth credentials accessed")
    return 0

if __name__=="__main__":sys.exit(main())
