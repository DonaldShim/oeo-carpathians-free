# C-Lab OAuth Gateway V1 — Gate 0 physical handoff (2026-10-28)

This is a **cumulative** version of the 18-file V1 ZIP plus a read-only executable production admission script and 3 regression tests. The original server implementation has not been replaced or declared production-ready.

## Executed observations

- 25/25 locally replayed Python tests passed, including new fail-closed deployment checks.
- In the authorized GCP project, an isolated *service account* was physically created: `c-lab-oauth-gateway-v1@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com`.
- Its Secret Manager key/version creation **was blocked** by the tool safety layer. A read-only GCP follow-up found no Gateway secret resource. No secret key is claimed to exist.
- Cloud SQL Admin API is not enabled in the canonical project and there is no independently verified dedicated PostgreSQL instance.
- The Render workspace already has its sole Free Postgres database, used by **C-Lab OAuth Canary**, due for expiry 2026-11-24. Do not reuse or modify it; it is not an isolated persistent Gateway DB and has no free-tier backups.
- Existing production C-Lab retains ready revision `c-lab-gcp-control-custody-v1-prod-20261020`; the new Gateway does not have an HTTPS endpoint. Google client secret/registered Google callback have not been verified.
- The old V11.1 synthetic test Cloud Run service remains distinct from this Gateway; do not swap its image into production.

## Gate replay (safe read-only)

From an authorized runtime with `gcloud` CLI:

```bash
python -m gateway.deploy_gate --output GATEWAY_ADMISSION_READBACK.json
```

The script **never reads secret values**, creates resources, or executes `gcloud auth login`. It verifies metadata only. Current result must remain OPEN until the external evidence is supplied. `free_trial_current_ui`, Google callback registration, dedicated DB with backup, and genuine Google/ChatGPT refresh are intentionally **not machine-affirmed** by this script.

## Required real-world closure

1. Prove backed-up, isolated PostgreSQL, sustainable charges within approved trial/billing policy and direct GCP connectivity.
2. Create independent Secret Manager secrets via authorized secure secret-management workflow; never expose values in chat/code/logs.
3. Register the exact chosen Gateway HTTPS `/google/callback` on a Google OAuth **Web application** client, verify its real secret is present only in Secret Manager.
4. Build and deploy the immutable Gateway image on a separate domain, with controlled IAM, ingress, TLS, rate limiting and no production plugin changes; run migration on the isolated Postgres instance.
5. Perform actual Google consent and observe the Google refresh grant followed by a C-Lab read **after actual Google access expiry**.
6. Connect ChatGPT to the Gateway using a supported registration path; observe *its* refresh grant and read after actual ChatGPT access expiry, with no synthetic substitutions.
7. Confirm production controls, rollback, bounded resource use. Only then consider cutover.

No full deployment or real Google/ChatGPT refresh was executed in this state.
