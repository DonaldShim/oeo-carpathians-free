# C-Lab OAuth Gateway — Gate 0 physical execution readback (2026-10-28 08:00 UTC)

**Outcome:** PARTIAL BUILD + LIVE ISOLATED IDENTITY; **NOT** a deployed OAuth Gateway. The original 18-file V1 executable source package has been extended in the conversation with read-only admission tooling, 3 new regression tests, and an evidence ledger. The cumulative ZIP in the conversation (not uploaded here as a GitHub asset) is:

- `C_LAB_OAUTH_GATEWAY_V1_GATE0_CUMULATIVE_20261028.zip`
- ZIP SHA256: `2be35764ae6da8be8dcf50bd02b8d3af5c58cc7954ad0b3c659203a9cf976c67`
- 22 files, ZIP CRC PASS, per-file SHA-256 verified.
- `python -m pytest -q`: **25/25 PASS** (local mocks; no live Google or ChatGPT consent).

## Real executed Google Cloud changes

Authorized MeAnDeR RDC gcloud physically **CREATED**:

`c-lab-oauth-gateway-v1@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com`

via `gcloud iam service-accounts create`, subsequent describe returned exact email. No project-level IAM grants made to it. No Cloud Run Gateway service created, no Cloud SQL created, no production traffic moved.

## Independently verified live blockers

- GCP billing project `project-4e9f56f4-a524-4759-91f` is linked to `billingAccounts/01117F-2FB3E2-31D263` with `billingEnabled=true`, but **a live 2026-10-28 Free Trial/remaining credit attestation was not obtained**. A billing link is not evidence against out-of-credit or Paid upgrade.
- `sqladmin.googleapis.com` is absent from `gcloud services list --enabled`. Dedicated PostgreSQL with backup not verified.
- In Render workspace `tea-db0vbck9v7es73d6mms0`, there is exactly one existing free PostgreSQL `c-lab-oauth-canary-store-20261025`, created Oct 25, expires 2026-11-24. It is used by distinct OAuth Canary; free Render permits **one** active free DB per workspace, has no managed backups. **Must not reuse it** for gateway.
- No Gateway Secret Manager secrets appeared in GCP metadata reads. An attempted key/version creation flow was **BLOCKED BY TOOL SAFETY**; do not claim a key exists or route around the block.
- OAuth Web Client secret and the precise Google callback registration for this new gateway were **not accessible/verified**. OAuth consent inherently needs a separate real end-user authorization step.
- The user-created Codex-only private OAuth probe does **not** expose a usable tool in the current ChatGPT chat. Even a functioning Gateway is not end-to-end ChatGPT-connected until its integration path is supported and exercised.
- Independent production C-Lab read 2026-10-28 08:00:48 UTC: `get_control_health.ok=true`, `get_fabric_health.ok=true`, ingress and runtime HTTP 200. Production ready revision unchanged from `c-lab-gcp-control-custody-v1-prod-20261020`.

## Explicit statuses

`ISOLATED_SA=AFFIRMED`; `LOCAL_EXECUTABLE_GATES=25/25_PASS`; `DEDICATED_POSTGRES=OPEN`; `GATEWAY_ENCRYPTION_KEY_IN_SECRET_MANAGER=OPEN`; `GOOGLE_OAUTH_CALLBACK_AND_CLIENT_SECRET=OPEN`; `HTTPS_GATEWAY_DEPLOYMENT=NOT_EXECUTED`; `GOOGLE_REAL_REFRESH=OPEN`; `CHATGPT_POST_EXPIRY_REFRESH=OPEN`; `PRODUCTION_CUTOVER=NOT_EXECUTED`.

**Next authorized move**: obtain a bounded, backed-up PostgreSQL plan and live Free Trial costs, register the exact Google Web Client HTTPS callback through an authorized method, complete isolated Secret Manager setup without disclosing values, then deploy signed immutable Gateway image on separate domain, run real Google consent and both independently attributable expiration/refresh/read tests. There are no live OAuth proof objects to report yet.

Reference: https://docs.cloud.google.com/sql/docs/postgres/connect-run ; https://render.com/docs/free ; https://developers.google.com/identity/protocols/oauth2/web-server
