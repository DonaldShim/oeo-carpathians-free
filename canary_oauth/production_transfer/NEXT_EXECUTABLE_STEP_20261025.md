# Exact production OAuth source discovery — 2026-10-25

Status **OPEN / AUTHORITATIVE_OAUTH_CONFIGURATION_ACCESS**. No change to production C-Lab, Fabric, IAM, scientific code, jobs or ChatGPT connection.

## Verified evidence
- Native connected C-Lab GCP Control 1.0.0: `get_control_health: ok=true`; Fabric `v54-ingress` and `fabric-runtime`: healthy, HTTP 200.
- Production app-backed Plugin Creator package contains `.app.json` App ID and compatibility manifest; current Google authorization request parameters and source are NOT exposed.
- GCP Control has no OAuth-layer source/provenance inspection tool. Its `get_transport_release_provenance(publisher_validator)` is not admissible for OAuth.
- Chat-mode connected Browser refused privileged Cloud Console context; no authority to navigate or execute.
- Official Google docs require `access_type=offline` in the Google authorization request for offline refresh. OpenAI published Plugin manifest docs do not advertise an arbitrary `authorizationParams` setting. Whether an `authorizationUrl` override carries query parameters must be explicitly validated before any production edit.

## Next direct execute command

From an **already authorized Google Cloud computer** or ChatGPT Work Cloud Browser with read-only Cloud Run and Cloud Build access:

```bash
python C_LAB_PROD_OAUTH_PROVENANCE_READONLY_20261025.py \
  --project project-4e9f56f4-a524-4759-91f \
  --region europe-west1 \
  --service c-lab-gcp-control \
  --output clab_oauth_provenance_sanitized.json
```

The companion script is in this conversation's downloadable package `C_LAB_PRODUCTION_OAUTH_SOURCE_DISCOVERY_20261025.zip`. It whitelists exactly this project/region/service, calls only `gcloud run services describe`, `gcloud run revisions describe` and, if build-id is available, `gcloud builds describe`. It prints no env values, client secrets, tokens, accounts or Cloud Build steps.

Script verified: **8/8 mock self-checks PASS**. Real Cloud Run retrieval **NOT EXECUTED** in this runtime: `gcloud` executable absent (FileNotFoundError). Do not claim this is a production outage.

## Closure gate
Authoritative revision + image digest + source commit/archive + OAuth authority and exact auth URL parameters → isolate a minimal Google offline request candidate → replay actual native Google refresh and protected C-Lab MCP read after access expiration → safe cutover with 0%-traffic candidate and rollback.

No production cutover until the exact source and connection auth contract are established. Never send secrets to chat or use RDC for canonical infrastructure.
