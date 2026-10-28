# C-Lab OAuth Gateway V2 — verified infrastructure and source (2026-10-28)

This is a precise physical execution ledger. **The end-to-end Google OAuth/ChatGPT gateway was not deployed or authorized.**

## Real mutations — independent readback

- Created Google Cloud Firestore **default** database (Standard, Firestore Native) at `eur3` in `project-4e9f56f4-a524-4759-91f`. Google reported `freeTier=true`, PESSIMISTIC concurrency, delete protection ENABLED, created `2026-10-28T08:26:07.006249Z`.
- Enabled `firestore.googleapis.com` API.
- Verified actual Firestore REST **write/read/delete** of test-only document, then conditional `currentDocument.exists=false` write PASS; duplicate atomic write HTTP 409; readback PASS, test doc deleted. No raw credentials written.
- Dedicated service identity already created `c-lab-oauth-gateway-v1@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com` has **conditional** `roles/datastore.user` IAM, **restricted** to `resource.name == "projects/project-4e9f56f4-a524-4759-91f/databases/(default)"`; independent CLI policy readback confirmed. No Owner/Editor or C-Fabric controls.
- Google Drive connected-user folder created and verified by API: https://drive.google.com/drive/folders/1nvWdPEWl8_Gi2B5xrnaZ1osNpeAq2Jt8 — **folder only, no active encrypted backups yet**.
- Production C-Lab untouched; no Cloud Run gateway service deployed, no traffic redirected.

## Executable source artifact (not yet committed to GitHub)

`C_LAB_OAUTH_GATEWAY_V2_FIRESTORE_DRIVE_20261028.zip` in the current ChatGPT conversation's artifact surface. SHA256 `e6104d277691a01c1b59e744280b8b57137229ba532ea4e4269b49863ac4e957`; 33 files and a per-file SHA256 manifest. Full cumulative original V1.2 source preserved.

V2 adds:
- `gateway/firestore_store.py`: Firestore transactional one-shot auth flow/code, hashed access/refresh token storage, atomic refresh rotation and replay revocation, atomic admission limiter, leased Google token refresh. Uses standard Cloud Run ADC, no SA key JSON.
- `gateway/firestore_app.py`: real Google login/verification + read-only 3-tool MCP proxy, OAuth discovery and RFC-style bearer challenge. Configuration **fails closed** without secrets.
- `gateway/drive_backup.py`: separately encrypted Drive archive transport, digest and returned metadata verification, hard-deny raw credential keys; requires real user-delegated `drive.file` OAuth. No live backup transaction.
- `Dockerfile.firestore`, `requirements.firestore.txt`, `tests/test_firestore_gateway.py`, `tests/test_drive_backup.py`, `README_FIRESTORE_DRIVE_GATE.md`.

Independent local verification: `PYTHONPATH=. pytest -q --disable-warnings` -> **40 passed**, 0 failed. Includes Firestore behavior under **in-memory transaction stand-in**, and Drive upload against HTTP mock only. This does not constitute Cloud Run E2E or Google-issued refresh.

## Unresolved mandatory external dependencies

1. Google Auth Platform standard OAuth Web Client creation or approved redirect URI update and capture of client secret into Secret Manager. Google's supported process uses an authenticated **Console** step; general programmatic Web OAuth client creation/update is not available through GCP CLI. A former IAP API was shut down in March 2026 and is not an alternative. Do not steal cookies, reuse a secret, or silently change canonical client's redirect URI.
2. ChatGPT Web's custom MCP integration remains unavailable in this conversation. A Codex-only plugin does not establish ChatGPT issuance or refresh.
3. A Cloud Run gateway HTTPS service has **not** been deployed. Missing real Google client credentials and Secret Manager key version; previous key-version creation attempt was blocked by safety controls. No placeholders accepted.
4. Cloud Run service identity cannot write to the **personal** Google Drive folder by itself because service accounts cannot own My Drive files. A separate delegated human `drive.file` OAuth grant or Workspace Shared Drive is required. The folder is not live durability.

## Closure statuses

`FIRESTORE_ENGINE = AFFIRMED (real)`;
`FIRESTORE_CONDITIONAL_IAM = AFFIRMED (real)`;
`FIRESTORE_ATOMIC_CAS = AFFIRMED (real)`;
`GATEWAY_V2_SOURCE_TESTS = AFFIRMED (local 40/40)`;
`GOOGLE_DRIVE_FOLDER = AFFIRMED`;
`DRIVE_UNATTENDED_BACKUP = OPEN`;
`HTTPS_GATEWAY = OPEN`;
`REAL_GOOGLE_REFRESH = OPEN`;
`REAL_CHATGPT_REFRESH = OPEN`;
`PRODUCTION_CUTOVER = NOT_EXECUTED`.

Sources: https://firebase.google.com/docs/firestore/quotas ; https://developers.google.com/workspace/drive/api/guides/handle-errors ; https://support.google.com/cloud/answer/15549257 .
