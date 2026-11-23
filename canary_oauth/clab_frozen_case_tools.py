"""RDC-independent, OAuth-scoped, read-only frozen scientific case adapter.

Reads original October 2026 C-Lab SHA-certified archive metadata from a dedicated
Neon database with a SELECT-only role. It never starts jobs or accesses live GCS.
"""
import hashlib
import json
import os
import re
from urllib.parse import urlparse

OPS=("get_frozen_case_state","get_frozen_batch_artifact")
CASE_PATTERN=r"^[A-Za-z0-9._-]{1,180}$"
INV_PATTERN=r"^[A-Za-z0-9_-]{1,100}$"
INPUTS={
 "get_frozen_case_state":{
  "type":"object","properties":{"case_ref":{"type":"string","pattern":CASE_PATTERN,"maxLength":180}},
  "required":["case_ref"],"additionalProperties":False},
 "get_frozen_batch_artifact":{
  "type":"object","properties":{
    "invocation_id":{"type":"string","pattern":INV_PATTERN,"maxLength":100},
    "artifact_name":{"type":"string","enum":["execution.json","smoke.json"]}},
  "required":["invocation_id","artifact_name"],"additionalProperties":False},
}
DESCRIPTIONS={
 "get_frozen_case_state":"Read a SHA-certified C-Lab scientific carrier contract from the immutable October 2026 mirror. Historical only; never reports current cloud state.",
 "get_frozen_batch_artifact":"Read one SHA-verified historical JSON receipt from the archived October 2026 C-Lab Batch results; never executes jobs.",
}
_CASE_SQL="""SELECT domain,case_ref,artifact_sha256,archive_bytes,archive_format,
 snapshot_date::text AS snapshot_date,verified_at::text AS verified_at,
 declared_scientific_contract::text AS contract_json,
 has_scientific_manifest,has_carrier_spec,has_registration_request,evidence_status
 FROM public.get_frozen_case_state_v1(%s) ORDER BY domain,artifact_sha256 LIMIT 20"""
_ARTIFACT_SQL="""SELECT invocation_id,artifact_name,artifact_sha256,
 body_utf8,encode(sha256(convert_to(body_utf8,'UTF8')),'hex') AS server_sha256,
 verified_at::text AS verified_at
 FROM public.frozen_batch_json_artifacts
 WHERE invocation_id=%s AND artifact_name=%s LIMIT 1"""

def args_ok(name,args):
    if not isinstance(args,dict) or name not in OPS:
        return False
    if name=="get_frozen_case_state":
        return set(args)=={"case_ref"} and isinstance(args["case_ref"],str) and bool(re.fullmatch(CASE_PATTERN,args["case_ref"]))
    return set(args)=={"invocation_id","artifact_name"} and isinstance(args["invocation_id"],str) and bool(re.fullmatch(INV_PATTERN,args["invocation_id"])) and args["artifact_name"] in ("execution.json","smoke.json")

def query(name,args):
    """Returns (success, bounded object) with no exception strings/credentials."""
    if not args_ok(name,args):
        return False,{"availability":"INVALID_ARGUMENTS","method":name}
    uri=os.environ.get("CLAB_FROZEN_CASE_DATABASE_URL","")
    try:
        url=urlparse(uri)
        if not (url.scheme=="postgresql" and url.hostname and
                url.hostname.endswith(".neon.tech") and
                url.path=="/clab_frozen_case_registry_v1"):
            return False,{"availability":"ARCHIVE_DATABASE_NOT_CONFIGURED","method":name}
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(uri,connect_timeout=6,sslmode="require",row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout='5000ms'")
                if name=="get_frozen_case_state":
                    cur.execute(_CASE_SQL,(args["case_ref"],))
                    rows=cur.fetchall()
                else:
                    cur.execute(_ARTIFACT_SQL,(args["invocation_id"],args["artifact_name"]))
                    rows=cur.fetchall()
        if name=="get_frozen_case_state":
            records=[]
            for row in rows:
                record={k:v for k,v in row.items() if k!="contract_json"}
                record["declared_scientific_contract"]=json.loads(row["contract_json"]) if row["contract_json"] is not None else None
                records.append(record)
            value={"schema":"CLAB_FROZEN_CASE_READBACK_V1","method":name,
                   "case_ref":args["case_ref"],"found":bool(records),"records":records,
                   "source":"Neon frozen C-Lab Oct 2026 SHA-verified mirror",
                   "live_google_cloud":False,"scientific_jobs_executed":False}
        else:
            row=rows[0] if rows else None
            if row is not None:
                checked=hashlib.sha256(row["body_utf8"].encode("utf-8")).hexdigest()
                if checked!=row["artifact_sha256"] or checked!=row["server_sha256"]:
                    return False,{"availability":"ARCHIVED_ARTIFACT_INTEGRITY_FAILED","method":name}
                content=json.loads(row["body_utf8"])
                value={"schema":"CLAB_FROZEN_BATCH_ARTIFACT_V1","method":name,
                       "found":True,"invocation_id":row["invocation_id"],
                       "artifact_name":row["artifact_name"],"sha256":checked,
                       "verified_at":row["verified_at"],"artifact_json":content,
                       "source":"Neon frozen C-Lab Oct 2026 SHA-verified mirror",
                       "live_google_cloud":False,"scientific_jobs_executed":False}
            else:
                value={"schema":"CLAB_FROZEN_BATCH_ARTIFACT_V1","method":name,
                       "found":False,"invocation_id":args["invocation_id"],
                       "artifact_name":args["artifact_name"],
                       "live_google_cloud":False,"scientific_jobs_executed":False}
        if len(json.dumps(value,ensure_ascii=False))>22000:
            return False,{"availability":"ARCHIVED_RESULT_SIZE_REJECTED","method":name}
        return True,value
    except Exception:
        # Do not leak database host credentials, internal SQL or other exceptions.
        return False,{"availability":"ARCHIVE_DATABASE_UNAVAILABLE","method":name}
