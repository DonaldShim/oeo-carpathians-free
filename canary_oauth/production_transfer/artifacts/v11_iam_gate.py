#!/usr/bin/env python3
"""C-Lab V11 exact IAM readback, fail-closed optional one-bucket grant. No builds."""
import argparse, datetime as dt, json, pathlib, shutil, subprocess, sys, uuid
P="project-4e9f56f4-a524-4759-91f"
B=P+"_cloudbuild"; BUCKET="gs://"+B
SA="855271818322-compute@developer.gserviceaccount.com"
MEMBER="serviceAccount:"+SA; ROLE="roles/storage.bucketViewer"
RESOURCE="//storage.googleapis.com/projects/_/buckets/"+B
SERVICE="c-lab-gcp-control"; REGION="europe-west1"
PROD="c-lab-gcp-control-custody-v1-prod-20261020"

def call(args):
    p=subprocess.run(["gcloud",*args],capture_output=True,text=True)
    if p.returncode: raise RuntimeError("GCLOUD_FAILED: "+" ".join(args)+": "+p.stderr.strip()[:400])
    return p.stdout

def read_json(args):
    return json.loads(call([*args,"--format=json"]))

def dump(path,obj):
    path.write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")

def has_role(policy,role,member):
    return any(x.get("role")==role and member in x.get("members",[]) and not x.get("condition")
               for x in policy.get("bindings",[]))

def capture():
    if call(["config","get-value","project"]).strip()!=P: raise RuntimeError("WRONG_ACTIVE_PROJECT")
    b=read_json(["storage","buckets","describe",BUCKET])
    if b.get("name")!=B or str(b.get("location","")).upper()!="US": raise RuntimeError("BUCKET_IDENTITY_MISMATCH")
    d={"bucket":b,
       "bucket_policy":read_json(["storage","buckets","get-iam-policy",BUCKET]),
       "project_policy":read_json(["projects","get-iam-policy",P]),
       "production":read_json(["run","services","describe",SERVICE,"--region="+REGION,"--project="+P]),
       "probes":{}}
    for permission in ("storage.buckets.get",):
        d["probes"][permission]=read_json(["policy-intelligence","troubleshoot-policy","iam",RESOURCE,
           "--principal-email="+SA,"--permission="+permission,"--project="+P])
    return d

def gate(d):
    reasons=[]
    traffic={x.get("revisionName"):x.get("percent",0)
       for x in d["production"].get("status",{}).get("traffic",[]) if x.get("percent",0)>0}
    if traffic!={PROD:100}: reasons.append("PRODUCTION_TRAFFIC_DRIFT")
    if not has_role(d["project_policy"],"roles/storage.objectViewer",MEMBER):
        reasons.append("OBJECT_VIEWER_NOT_CONFIRMED")
    if has_role(d["bucket_policy"],ROLE,MEMBER):
        reasons.append("DIRECT_BUCKET_GRANT_ALREADY_PRESENT")
    states={}
    for permission in ("storage.buckets.get",):
        x=d["probes"][permission]; t=x.get("accessTuple",{})
        if t.get("principal")!=SA or t.get("fullResourceName")!=RESOURCE or t.get("permission")!=permission:
            reasons.append("INVALID_TROUBLESHOOT_TUPLE_"+permission)
        states[permission]=x.get("overallAccessState","UNKNOWN")
    if states["storage.buckets.get"]!="CANNOT_ACCESS": reasons.append("BUCKETS_GET_NOT_CERTIFIED_MISSING")
    p=d["probes"]["storage.buckets.get"]
    if p.get("allowPolicyExplanation",{}).get("allowAccessState")!="ALLOW_ACCESS_STATE_NOT_GRANTED":
        reasons.append("ALLOW_POLICY_NOT_SIMPLE_MISSING_GRANT")
    if p.get("denyPolicyExplanation",{}).get("denyAccessState")!="DENY_ACCESS_STATE_NOT_DENIED":
        reasons.append("DENY_POLICY_NOT_CERTIFIED_CLEAR")
    return {"admissible":not reasons,"reasons":reasons,"states":states,"production_traffic":traffic}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("read","apply"),default="read")
    parser.add_argument("--acknowledge-bucket-grant",action="store_true")
    args=parser.parse_args()
    if args.mode=="apply" and not args.acknowledge_bucket_grant:
        raise RuntimeError("APPLY_REQUIRES_--acknowledge-bucket-grant")
    if not shutil.which("gcloud"): raise RuntimeError("AUTHORIZED_GCLOUD_RUNTIME_UNAVAILABLE")
    output=pathlib.Path.home()/("CLAB_V11_IAM_"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")+
             "_"+uuid.uuid4().hex[:6])
    output.mkdir()
    receipt={"at":dt.datetime.now(dt.timezone.utc).isoformat(),"mode":args.mode,
        "bucket":B,"principal":SA,"proposed_role":ROLE,"mutation_performed":False,
        "build_submitted":False,"deployment_performed":False}
    try:
        d=capture()
        for k,v in d.items(): dump(output/(k+".json"),v)
        g=gate(d); receipt["gate"]=g
        receipt["bucket_etag_before"]=d["bucket_policy"].get("etag")
        if args.mode=="read":
            receipt["outcome"]="READBACK_COMPLETE_NO_MUTATION"
        elif not g["admissible"]:
            receipt["outcome"]="STOP_INADMISSIBLE_GRANT"
        else:
            fresh=read_json(["storage","buckets","get-iam-policy",BUCKET])
            dump(output/"bucket_policy_immediate_pregrant.json",fresh)
            if fresh.get("etag")!=d["bucket_policy"].get("etag") or fresh.get("bindings")!=d["bucket_policy"].get("bindings"):
                receipt["outcome"]="STOP_POLICY_CHANGED_BEFORE_GRANT"
            else:
                call(["storage","buckets","add-iam-policy-binding",BUCKET,
                    "--member="+MEMBER,"--role="+ROLE])
                receipt["mutation_performed"]=True
                post=read_json(["storage","buckets","get-iam-policy",BUCKET])
                dump(output/"bucket_policy_after.json",post)
                receipt["bucket_etag_after"]=post.get("etag")
                receipt["role_added_observed"]=has_role(post,ROLE,MEMBER)
                receipt["outcome"]="GRANT_PRESENT_EFFECT_OPEN" if receipt["role_added_observed"] else "STOP_GRANT_READBACK_FAILED"
                after=read_json(["policy-intelligence","troubleshoot-policy","iam",RESOURCE,
                     "--principal-email="+SA,"--permission=storage.buckets.get","--project="+P])
                dump(output/"effective_buckets_get_after.json",after)
                receipt["effective_buckets_get_after"]=after.get("overallAccessState")
                if receipt["role_added_observed"] and after.get("overallAccessState")=="CAN_ACCESS":
                    receipt["outcome"]="BUCKET_SCOPED_GRANT_OBSERVED"
                prod_after=read_json(["run","services","describe",SERVICE,
                    "--region="+REGION,"--project="+P])
                dump(output/"production_after.json",prod_after)
                receipt["production_traffic_preserved"]=(
                    prod_after.get("status",{}).get("traffic")==d["production"].get("status",{}).get("traffic"))
                if not receipt["production_traffic_preserved"]:
                    receipt["outcome"]="STOP_PRODUCTION_TRAFFIC_CHANGED"
                receipt["rollback_command"]="gcloud storage buckets remove-iam-policy-binding "+BUCKET+" --member="+MEMBER+" --role="+ROLE
    except Exception as e:
        receipt["outcome"]="STOP_TOOL_ERROR"; receipt["error"]=str(e)[:600]
    finally:
        receipt["completed_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
        dump(output/"IAM_GATE_RECEIPT.json",receipt)
        print(json.dumps({"receipt":str(output/"IAM_GATE_RECEIPT.json"),**receipt},indent=2,ensure_ascii=False))
    if receipt["outcome"].startswith("STOP"): sys.exit(3)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("STOP:",str(e)[:400],file=sys.stderr); sys.exit(2)
