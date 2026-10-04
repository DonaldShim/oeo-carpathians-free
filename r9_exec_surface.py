import os, sys, json, hashlib, tarfile, tempfile, shutil, subprocess, threading, pathlib, urllib.request, urllib.error, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

EXPECTED_BUNDLE_SHA = "642af75286a62c4aa94a1fcd08ddfc8ef17b8628f1fcbec89f8bd4da688538c4"
EXPECTED_SOURCE_SHA = "79cc1deb6fac2de04f5f3432d08a0495673cc98beb70c3785704f9b208271d22"
CASE_ID = "C_ASYM_V306"
CARRIER_ID = "V306R9_RANK3_EXHAUSTIVE_CEGAR_OUTPUTFIX3"
PORT = int(os.environ.get("PORT", "10000"))

STATE = {
    "status": "WAITING_FOR_SIGNED_URL",
    "case_id": CASE_ID,
    "carrier_id": CARRIER_ID,
    "bundle_sha256_expected": EXPECTED_BUNDLE_SHA,
    "scientific_source_sha256_expected": EXPECTED_SOURCE_SHA,
    "scientific_started": False,
    "scientific_finished": False,
    "certificate": None,
    "error": None,
}

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def safe_extract_tar(tar_path, out_dir):
    out_root = pathlib.Path(out_dir).resolve()
    with tarfile.open(tar_path, "r:gz") as tf:
        for m in tf.getmembers():
            target = (out_root / m.name).resolve()
            if not str(target).startswith(str(out_root) + os.sep) and target != out_root:
                raise RuntimeError("TAR_PATH_TRAVERSAL")
            if m.islnk() or m.issym():
                link_target = (target.parent / m.linkname).resolve()
                if not str(link_target).startswith(str(out_root) + os.sep) and link_target != out_root:
                    raise RuntimeError("TAR_LINK_ESCAPE")
        tf.extractall(out_root)

def find_exact(root, name):
    matches = [p for p in pathlib.Path(root).rglob(name) if p.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"EXPECTED_SINGLE_{name}_FOUND_{len(matches)}")
    return matches[0]

def load_json_if_exists(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def recursive_find_key(obj, keys):
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                return obj[k]
        for v in obj.values():
            r = recursive_find_key(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = recursive_find_key(v, keys)
            if r is not None:
                return r
    return None

def maybe_install_requirements(root):
    candidates = list(pathlib.Path(root).rglob("requirements.txt"))
    if not candidates:
        return {"attempted": False, "returncode": None}
    req = sorted(candidates, key=lambda p: len(p.parts))[0]
    p = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        cwd=str(req.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
    )
    return {
        "attempted": True,
        "returncode": p.returncode,
        "requirements_path": str(req.relative_to(root)),
        "log_tail": p.stdout[-4000:],
    }

def run_science():
    signed_url = os.environ.get("R9_SIGNED_URL", "").strip()
    if not signed_url:
        return

    try:
        parsed = urlparse(signed_url)
        if parsed.scheme != "https" or parsed.hostname != "storage.googleapis.com":
            raise RuntimeError("SIGNED_URL_HOST_REJECTED")

        STATE["status"] = "DOWNLOADING"
        STATE["scientific_started"] = False
        work = tempfile.mkdtemp(prefix="r9_exact_")
        archive = os.path.join(work, "bundle.tar.gz")

        req = urllib.request.Request(signed_url, method="GET")
        with urllib.request.urlopen(req, timeout=60) as r, open(archive, "wb") as out:
            total = 0
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 128 * 1024 * 1024:
                    raise RuntimeError("BUNDLE_TOO_LARGE")
                out.write(chunk)

        STATE["downloaded_bytes"] = os.path.getsize(archive)
        actual_bundle_sha = sha256_file(archive)
        STATE["bundle_sha256_actual"] = actual_bundle_sha
        STATE["bundle_sha256_verified"] = actual_bundle_sha == EXPECTED_BUNDLE_SHA
        if actual_bundle_sha != EXPECTED_BUNDLE_SHA:
            raise RuntimeError("BUNDLE_SHA_MISMATCH")

        extract_dir = os.path.join(work, "bundle")
        os.makedirs(extract_dir, exist_ok=True)
        safe_extract_tar(archive, extract_dir)

        source = find_exact(extract_dir, "v306r9.py")
        actual_source_sha = sha256_file(source)
        STATE["scientific_source_path"] = str(source.relative_to(extract_dir))
        STATE["scientific_source_sha256_actual"] = actual_source_sha
        STATE["scientific_source_sha256_verified"] = actual_source_sha == EXPECTED_SOURCE_SHA
        if actual_source_sha != EXPECTED_SOURCE_SHA:
            raise RuntimeError("SCIENTIFIC_SOURCE_SHA_MISMATCH")

        install = maybe_install_requirements(extract_dir)
        STATE["requirements_install"] = install
        if install["attempted"] and install["returncode"] != 0:
            raise RuntimeError("REQUIREMENTS_INSTALL_FAILED")

        STATE["status"] = "RUNNING_R9"
        STATE["scientific_started"] = True
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(source)],
            cwd=str(source.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=7200,
            env=dict(os.environ),
        )
        elapsed = time.time() - t0
        STATE["scientific_returncode"] = proc.returncode
        STATE["scientific_elapsed_seconds"] = elapsed
        STATE["stdout_tail"] = proc.stdout[-12000:]
        STATE["stderr_tail"] = proc.stderr[-12000:]

        all_json = {}
        for p in pathlib.Path(extract_dir).rglob("*.json"):
            if p.is_file():
                obj = load_json_if_exists(p)
                if obj is not None:
                    all_json[str(p.relative_to(extract_dir))] = obj

        result_candidates = []
        for rel, obj in all_json.items():
            base = pathlib.Path(rel).name
            if base in ("SCIENTIFIC_RESULT.json", "V306R9_RANK3_EXHAUSTIVE_CEGAR.json"):
                result_candidates.append((rel, obj))

        result_hashes = {}
        for rel, _ in result_candidates:
            result_hashes[rel] = sha256_file(pathlib.Path(extract_dir) / rel)

        aggregate = [obj for _, obj in result_candidates]
        triples_evaluated = recursive_find_key(aggregate, ["triples_evaluated", "evaluated_triples", "n_triples_evaluated"])
        closure_found = recursive_find_key(aggregate, ["closure_found", "closed", "closure"])
        exhausted = recursive_find_key(aggregate, ["exhausted", "search_exhausted", "all_triples_exhausted"])
        witness = recursive_find_key(aggregate, ["witness", "closure_witness", "selected_triple", "best_triple"])

        if isinstance(closure_found, dict):
            closure_found = None
        if isinstance(exhausted, dict):
            exhausted = None

        authoritative_exhaustion = (triples_evaluated == 8436 and closure_found is False)
        if exhausted is True and triples_evaluated != 8436 and closure_found is not True:
            authoritative_exhaustion = False

        cert = {
            "schema": "C_ASYM_V306_R9_EXECUTION_CERT_V1",
            "case_id": CASE_ID,
            "carrier_id": CARRIER_ID,
            "scope": "CELL15",
            "rank": 3,
            "candidate_pool_size": 38,
            "triples_total": 8436,
            "triples_evaluated": triples_evaluated,
            "closure_found": closure_found,
            "exhausted_reported": exhausted,
            "authoritative_exhaustion": authoritative_exhaustion,
            "hidden_endpoint_used": False,
            "rank_growth": False,
            "bundle_sha256": actual_bundle_sha,
            "scientific_source_sha256": actual_source_sha,
            "scientific_returncode": proc.returncode,
            "scientific_elapsed_seconds": elapsed,
            "result_sha256": result_hashes,
            "witness": witness,
        }

        cert_path = pathlib.Path(source.parent) / "R9_CERTIFICATE.json"
        cert_path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        cert["certificate_sha256"] = sha256_file(cert_path)

        STATE["certificate"] = cert
        STATE["scientific_finished"] = True
        STATE["status"] = "DONE" if proc.returncode == 0 else "R9_PROCESS_FAILED"

    except subprocess.TimeoutExpired:
        STATE["status"] = "R9_TIMEOUT"
        STATE["error"] = "R9_TIMEOUT"
    except Exception as e:
        STATE["status"] = "ERROR"
        STATE["error"] = f"{type(e).__name__}: {e}"
    finally:
        os.environ.pop("R9_SIGNED_URL", None)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return
    def do_GET(self):
        if self.path not in ("/", "/status"):
            self.send_response(404); self.end_headers(); return
        body = json.dumps(STATE, indent=2, sort_keys=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    if os.environ.get("R9_SIGNED_URL", "").strip():
        run_science()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

if __name__ == "__main__":
    main()
