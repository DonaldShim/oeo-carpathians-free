# C-Lab OAuth Gateway V2 — Firestore + Google Drive

**Status: source + local prototype. Not deployed as OAuth service.**

## Physical infrastructure completed on 2026-10-28

- Firestore API enabled in project `project-4e9f56f4-a524-4759-91f`.
- Firestore `(default)`, **Standard / Native**, location `eur3`, `freeTier=true`, `PESSIMISTIC` concurrency, **delete protection enabled**, created 2026-10-28T08:26:07Z.
- Cloud Firestore REST write → read → delete: PASS.
- Cloud Firestore REST conditional `currentDocument.exists=false` first write PASS, replay write HTTP 409, readback PASS, test document removed: PASS.
- Dedicated service account `c-lab-oauth-gateway-v1@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com` and conditional `roles/datastore.user` restricted to `projects/project-4e9f56f4-a524-4759-91f/databases/(default)` created by GCP CLI.
- User-owned private Google Drive backup folder `https://drive.google.com/drive/folders/1nvWdPEWl8_Gi2B5xrnaZ1osNpeAq2Jt8` created via connected Google Drive. No raw credentials uploaded or shared.

## Gateway V2 implementation

- `gateway/firestore_store.py`: Firestore transaction-backed flow single use, code single use, refresh rotation and replay-triggered grant revocation, OAuth access validity, Google refresh lease, per-source admission, and metadata-only audit events. Uses Application Default Credentials, no service-account key JSON.
- `gateway/firestore_app.py`: endpoint implementation bound to real Google OIDC verification and a strict 3-read-only-tool MCP allowlist.
- `gateway/drive_backup.py`: separately encrypted, hash-verified, bounded Drive archive transport; *never* used for live authorization transactions.
- `Dockerfile.firestore` and pinned-base requirements. No production C-Lab routes modified.
- Local test runner uses `pytest -q`; Firestore API model tests use a serializable in-memory mock; Drive upload tests use a mock HTTP transport. **Do not call these tests real Google refresh.**

## Exact deployment constraints

1. **Google OAuth Web Client registration:** Standard Google Web OAuth client credentials/redirect-URI registration require use of Google Auth Platform console (Google documents this as a console operation). Neither existing connected C-Lab plugin nor GCP CLI provides an authorized way to retrieve the secret. Cannot fill in placeholders or use old client secrets. A newly created client ID would need a separate, reviewed C-Lab audience allowlist change after full external gate.
2. **Secret Manager:** No real Google OAuth client secret or Gateway Fernet version in Secret Manager; the prior attempt to create a key version was blocked by tool safety. Do not attempt a bypass or claim secret configured.
3. **Google Drive runtime:** This folder is owned by the human Google Drive account. A Cloud Run service-account OAuth token cannot upload files to a personal My Drive folder because service accounts do not own storage. Production upload needs separate, delegated end-user OAuth with `drive.file` scope (or an organizational Shared Drive). No unattended delegated Drive access has been established.
4. **ChatGPT registration:** `get_host_staging_inspect` is still not exposed by the Codex-only earlier plugin in regular ChatGPT Web; no end-to-end ChatGPT OAuth result or post-expiry refresh attestation.
5. **Deploy:** Full new OAuth server Cloud Run image and tagged revision have **NOT** been deployed. A nonfunctional/placeholder Google client would only cause a real `redirect_uri_mismatch`; reject it as a live service.

## Gate labels

- `FIRESTORE_DURABLE_ATOMIC_PRIMITIVE`: AFFIRMED (real service)
- `FIRESTORE_GATEWAY_LOCAL_MOCK_REPLAY`: AFFIRMED (local test suite)
- `DRIVE_FOLDER`: AFFIRMED (real folder)
- `DRIVE_RUNTIME_ENCRYPTED_BACKUP`: OPEN (no delegated credential)
- `REAL_GOOGLE_OAUTH_REFRESH`: OPEN
- `REAL_CHATGPT_GATEWAY_REFRESH`: OPEN
- `PRODUCTION_CUTOVER`: NOT PERFORMED

Recovery: drop the isolated service-account's *conditional* Firestore data binding after ensuring any operator's responsibility for the new free Firestore database. Delete-protection blocks accidental database removal. Do not alter canonical C-Lab production or remove Canary.

Sources:
- https://developers.google.com/identity/protocols/oauth2/resources/best-practices
- https://support.google.com/cloud/answer/15549257
- https://developers.google.com/workspace/drive/api/guides/handle-errors
- https://firebase.google.com/docs/firestore/quotas
