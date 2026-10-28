# C-Lab OAuth Gateway V1.2 — cumulative replay and critical external gates (2026-10-28)

## Exact in-session reproducible local artifact

The full cumulative source package is `C_LAB_OAUTH_GATEWAY_V1_2_CUMULATIVE_20261028.zip` in the current ChatGPT conversation attachment surface. **This GitHub certificate does not contain the 24-file ZIP** and is not a source checkout substitute.

- ZIP SHA256: `8bf6d8d120211e090fb92e6b8bbd0ca2219bdb1027b2c61f4b9fd92224f68886`
- 24 files; ZIP CRC PASS; 23/23 individual file SHA256 entries PASS.
- Current local `PYTHONPATH=. pytest -q`: **26 passed / 0 failed / 0 warnings**.
- `python -m compileall -q gateway tests`: PASS.
- Original V1 + Gate0 sources and tests preserved; version V1.2 adds `CIMD_AND_CLOUD_GATE_20261028.md`, `README_GATE_V1_2.md` and a fail-closed MCP auth challenge patch/test.
- Patch: unauthenticated `/mcp` POST stays HTTP 401; its `WWW-Authenticate` now contains `resource_metadata`, `scope`, `error="invalid_token"`, and `error_description`. Body includes `_meta["mcp/www_authenticate"]` with the same challenge. Invalid callers never reach C-Lab.

## Live interoperability readback

- HTTPS read of public `https://chatgpt.com/oauth/client.json`: `client_id=https://chatgpt.com/oauth/client.json`, `redirect_uris=[https://chatgpt.com/connector_platform_oauth_redirect]`, `grant_types` includes authorization_code and refresh_token, and `token_endpoint_auth_methods_supported` contains none and private_key_jwt.
- Authorized GCP CLI read of currently deployed canonical `c-lab-gcp-control` **compared** (without printing the whitelist or any secret) its `OAUTH_ALLOWED_CLIENT_IDS` env entry against the previously approved Google Client ID: `ALLOWLIST_ENTRY_PRESENT=true`, `CLIENT_ID_COUNT=1`, `APPROVED_GOOGLE_CLIENT_IN_ALLOWLIST=true`, `SOURCE_KIND=inline_public_client_ids`. Production Ready revision remained `c-lab-gcp-control-custody-v1-prod-20261020`.
- These observations show the gateway's **existing-Client-ID choice is admissible in principle**, not possession of the needed Google Web Client Secret or registration of a new Google redirect URI. Creating a new Google client would require a separate canonical C-Lab allowlist change.
- User has not supplied or authorized export of any private Google secret. No token values were fetched from existing sessions.

## Service readiness and explicit exact blockers

`LOCAL_OAUTH_CARRIER = AFFIRMED_SCOPED` (26 tests, mock Google and mock upstream).

`REAL_GOOGLE_OAUTH = OPEN`: new gateway HTTPS endpoint and Google Web Client callback must exist before real consent, with secret stored only in Secret Manager. The Google Cloud console Auth Platform manages Web Client redirect URIs; client secret is not available from attached App-backed C-Lab metadata. Don't fake a Google OAuth grant.

`DURABLE_POSTGRES = OPEN`: SQL Admin API was not enabled in project; Render's sole free 30-day Postgres is occupied by separate Canary and cannot serve as a durable isolated production store.

`GATEWAY_SECRET_MANAGER = OPEN`: Gateway service identity was physically created earlier; secret creation/versioning was blocked by the tools safety layer. No gateway secret versions exist per last GCP readback.

`CHATGPT_CONNECTOR_EXPOSURE = OPEN`: old Codex plugin not accessible in ChatGPT Web; Gateway may be built as a new plugin only once compatible registration/install is actually supported.

`PRODUCTION_CUTOVER = NOT_EXECUTED`. No Cloud Run routing, IAM, secrets, paid database, current OAuth connection or scientific jobs were changed during this V1.2 readback.

## Closure law

Do not label real Google refresh or native ChatGPT post-expiry read PASS on the strength of mocked 26/26, CIMD metadata, Google allowlist, or separate Canary successes. Only an actual paired Google refresh ledger **and** a ChatGPT post-expiry refresh + MCP read from the exact Gateway issuer can close that fruit.

Sources: https://developers.openai.com/plugins/build/auth ; https://developers.google.com/identity/protocols/oauth2/web-server
