#!/usr/bin/env python3
"""C-SCI V2: isolated, identity-bound execution of an immutable ARC3 registered ZIP.

No old Fabric publisher, validator, queue, or write credentials. Runtime uses only
objectCreator/objectViewer on the dedicated C-SCI bucket; never declares global ARC3.
"""
import hashlib
import io
import json
import os
import pathlib
import posixpath
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

BUCKET = "c-sci-clean-v1-855271818322"
CASE = "ARC3"
CARRIER = "ARC3-KOLO10-SELF-ATTRIBUTING-MECHANISM-FOUNDRY-V1"
SOURCE_SHA = "fe5aa32cd250e9268fe367c2136605f95eaa51b7aa58277b843bd58632a0bde3"
SOURCE = "sources/ARC3/" + CARRIER + "/" + SOURCE_SHA + ".zip"
RUN_ID = "c-sci-arc3-kolo10-20261029-r1"
PREFIX = "runs/" + RUN_ID + "/"
SCIENCE_TIMEOUT = 180


def H(data):
    return hashlib.sha256(data).hexdigest()


def data(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def token():
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}
    )
    with urllib.request.urlopen(req, timeout=8) as res:
        return json.load(res)["access_token"]


def read_object(name):
    url = "https://storage.googleapis.com/storage/v1/b/" + BUCKET + "/o/" + urllib.parse.quote(name, safe="") + "?alt=media"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read(20000000)


def cas_object(name, content):
    url = ("https://storage.googleapis.com/upload/storage/v1/b/" + BUCKET
           + "/o?uploadType=media&name=" + urllib.parse.quote(name, safe="")
           + "&ifGenerationMatch=0")
    req = urllib.request.Request(url, data=content, method="POST",
                                 headers={"Authorization": "Bearer " + token(),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            receipt = json.load(res)
        return str(receipt["generation"])
    except urllib.error.HTTPError as exc:
        if exc.code != 412:
            raise
        if read_object(name) != content:
            raise RuntimeError("IMMUTABLE_COLLISION:" + name)
        return "REPLAY_IDENTICAL"


def extract_verified(blob, target):
    if H(blob) != SOURCE_SHA:
        raise RuntimeError("REGISTERED_SOURCE_SHA_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        items = [x for x in z.infolist() if not x.is_dir()]
        if len(items) > 300:
            raise RuntimeError("SOURCE_MEMBER_LIMIT")
        paths = [x.filename for x in items]
        if len(paths) != len(set(paths)):
            raise RuntimeError("SOURCE_DUPLICATE_MEMBERS")
        if "MANIFEST_SHA256.json" not in paths or "runtime/run_v10.py" not in paths:
            raise RuntimeError("SOURCE_REQUIRED_MEMBERS_MISSING")
        manifest = json.loads(z.read("MANIFEST_SHA256.json"))
        stated = manifest["files"]
        if set(stated) != (set(paths) - {"MANIFEST_SHA256.json"}):
            raise RuntimeError("SOURCE_MANIFEST_SET_MISMATCH")
        total = 0
        for item in items:
            name = item.filename
            norm = posixpath.normpath(name)
            if (norm != name or name.startswith("/") or name.startswith("../")
                    or "\\" in name or ":" in name):
                raise RuntimeError("UNSAFE_SOURCE_PATH")
            if (item.external_attr >> 16) & 0o170000 == stat.S_IFLNK:
                raise RuntimeError("SOURCE_SYMLINK_FORBIDDEN")
            total += item.file_size
            if total > 25000000 or item.file_size > 5000000:
                raise RuntimeError("SOURCE_DECOMPRESSION_LIMIT")
            content = z.read(item)
            if name != "MANIFEST_SHA256.json":
                metadata = stated[name]
                if metadata["size"] != len(content) or metadata["sha256"] != H(content):
                    raise RuntimeError("SOURCE_INTERNAL_MANIFEST_MISMATCH")
            p = target / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
    spec = json.loads((target / "CARRIER_SPEC.json").read_text())
    if spec["carrier_id"] != CARRIER or spec["declared_scientific_output"] != "SCIENTIFIC_RESULT.json" or spec["hidden_endpoint_used"] is not False:
        raise RuntimeError("CARRIER_SPEC_MISMATCH")


def check_science(raw):
    result = json.loads(raw)
    if result.get("schema") != "C_LAB_SCIENTIFIC_RESULT_V1":
        raise RuntimeError("SCIENCE_SCHEMA_INVALID")
    claimed = result.get("semantic_sha256")
    unsigned = dict(result)
    unsigned.pop("semantic_sha256", None)
    semantic = H(json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str).encode())
    if claimed != semantic:
        raise RuntimeError("SCIENCE_SEMANTIC_HASH_INVALID")
    gates = result.get("hard_gate", {})
    if not isinstance(gates, dict) or gates.get("pass") is not True:
        raise RuntimeError("SCIENCE_HARD_GATE_NOT_PASS")
    if not all(x is True for k, x in gates.items() if k != "pass"):
        raise RuntimeError("SCIENCE_GATE_INCONSISTENT")
    if not result.get("status", "").startswith("AFFIRMED_SCOPED_"):
        raise RuntimeError("SCIENCE_SCOPE_NOT_AFFIRMED")
    arc = result.get("ARC3", {})
    spot = arc.get("fresh_spot_replay", {})
    q = spot.get("causal_quotient", {})
    raw_arm = spot.get("raw", {})
    if not (spot.get("scoped_credit_reproduced") is True
            and q.get("level_gain", 0) > 0
            and q.get("exact_duplicate_replay") is True
            and raw_arm.get("found") is False):
        raise RuntimeError("ARC3_FRESH_REPLAY_NOT_CREDITED")
    if not ("OPEN" in arc.get("scientific_status", "")
            and "OPEN" in result.get("RH", {}).get("scientific_status", "")):
        raise RuntimeError("GLOBAL_CLAIM_SCOPE_VIOLATION")
    if len(result.get("claim_boundary", [])) < 4:
        raise RuntimeError("PROOF_BOUNDARY_MISSING")
    return result, semantic


def main():
    blob = read_object(SOURCE)
    with tempfile.TemporaryDirectory(prefix="c_sci_arc3_") as tmp:
        root = pathlib.Path(tmp) / "source"
        root.mkdir()
        extract_verified(blob, root)
        output = pathlib.Path(tmp) / "outputs"
        output.mkdir()
        subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                        "--no-cache-dir", "numpy==1.26.4", "mpmath==1.3.0"],
                       check=True, capture_output=True, timeout=110)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "runtime") + os.pathsep + str(root / "public_runtime")
        env["C_LAB_OUTPUT_DIR"] = str(output)
        proc = subprocess.run([sys.executable, "-B", str(root / "runtime" / "run_v10.py")],
                              cwd=str(root), env=env, capture_output=True,
                              timeout=SCIENCE_TIMEOUT, check=False)
        if proc.returncode != 0:
            raise RuntimeError("SCIENTIFIC_EXECUTION_FAILED_RC_" + str(proc.returncode)
                               + "_STDERR_SHA_" + H(proc.stderr)[:16])
        result_path = output / "SCIENTIFIC_RESULT.json"
        if not result_path.is_file() or result_path.stat().st_size > 4000000:
            raise RuntimeError("SCIENCE_RESULT_ABSENT_OR_OVERSIZE")
        raw = result_path.read_bytes()
        result, semantic = check_science(raw)
        obj = cas_object(PREFIX + "SCIENTIFIC_RESULT.json", raw)
        receipt = {
            "schema": "C_SCI_TERMINAL_RECEIPT_V2",
            "run_id": RUN_ID,
            "case": CASE,
            "carrier_id": CARRIER,
            "input_sha256": SOURCE_SHA,
            "source_manifest_checked": True,
            "scientific_status": result["status"],
            "scoped_scientific_done": True,
            "new_unseen_arc3_goal": False,
            "scientific_result_sha256": H(raw),
            "scientific_result_bytes": len(raw),
            "scientific_semantic_sha256": semantic,
            "scientific_process_rc": proc.returncode,
            "publisher": "C_SCI_V2_OWN_WRAPPER_NOT_V54",
            "receipt_terminal": True
        }
        rec_bytes = data(receipt)
        rec = cas_object(PREFIX + "receipt.json", rec_bytes)
        print("C_SCI_V2_ARC3_SCOPED_DONE=true")
        print("SOURCE_SHA256=" + SOURCE_SHA)
        print("RESULT_SHA256=" + H(raw))
        print("RECEIPT_SHA256=" + H(rec_bytes))
        print("RESULT_GCS_GENERATION=" + obj)
        print("RECEIPT_GCS_GENERATION=" + rec)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Separate failure object; never fake the terminal scientific DONE receipt.
        reason = type(exc).__name__ + ":" + str(exc)[:180]
        fail = {"schema": "C_SCI_EXECUTION_FAILURE_V1", "run_id": RUN_ID,
                "carrier_id": CARRIER, "status": "INFRA_OR_SCIENCE_OPEN", "reason": reason}
        try:
            cas_object(PREFIX + "failure.json", data(fail))
        except Exception:
            pass
        print("C_SCI_V2_ARC3_DONE=false;error=" + reason, file=sys.stderr)
        sys.exit(2)
