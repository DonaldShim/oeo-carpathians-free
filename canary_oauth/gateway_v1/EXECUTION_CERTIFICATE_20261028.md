# C-Lab OAuth Gateway V1 — EXECUTABLE PROTOTYPE GATE (2026-10-28)

This is a **standalone OAuth 2.1 / PKCE Google-offline MCP read-only gateway PrototypeCandidate**, not a production cutover. A complete 18-file source+tests+Dockerfile package was generated as the conversation artifact `C_LAB_OAUTH_GATEWAY_V1_PROTOTYPE_20261028.zip`; the binary ZIP is **not contained in this GitHub commit**. Preserve or upload the full ZIP separately before attempting CI or Docker builds. The source ZIP is provided in the active ChatGPT conversation artifact surface, not at a publicly accessible GitHub URL.

## Physical local execution

- Test command: `PYTHONPATH=. pytest -q`
- **22/22 PASS**, 0 fails on local Python 3.13.5.
- Full Python compile PASS, ZIP CRC PASS, every source hash matches `SHA256_MANIFEST.json`.
- Runs use test Google/Upstream doubles, SQLite explicitly allowed only in dev, real FastAPI/SQLAlchemy/cryptography.
- The package contains `gateway/app.py`, `config.py`, `db.py`, `crypto.py`, `google.py`, `upstream.py`, `migrate.py`, 2 test suites, requirements, Dockerfile, runbook and security contract.

## Contract and security

- ChatGPT <-> Gateway OAuth 2.1 auth-code PKCE S256, exact pinned CIMD client id + ChatGPT callback allowlist + resource binding.
- Gateway -> Google OAuth code + PKCE, `access_type=offline`, explicit Google refresh required, verified Google OIDC subject/issuer/aud/nonce/email_verified.
- gateway refresh token rotation, replay revocation, one-use code, SHA256 token hashes, Fernet Google credential encryption, expiration, RFC7009-style revocation.
- Production PostgreSQL only; schema migration explicit; secrets from Secret Manager. No real tokens/secrets in artifact.
- MCP allowlist **only** `get_control_health`, `get_controller_status`, `get_fabric_health`, zero arguments, fixed canonical upstream address. All recovery/write/science tools blocked.
- No production changes made, no new Cloud Run deployment, no cloud SQL provision, no IAM changes.
- Existing C-Lab Cloud Secret Manager metadata review showed C-Lab general secrets, but no dedicated Gateway production secret. PostgreSQL Cloud SQL list did not yield a verified readback; do **not** claim database existing or absent.

## Closure

- LOCAL BUILD / MOCK REPLAY: **AFFIRMED**.
- INDEPENDENT CI / GHCR IMAGE: **OPEN, not executed** (binary package not uploaded to GitHub).
- GOOGLE LIVE AUTH / GOOGLE REFRESH / POST-EXPIRY C-LAB READ: **OPEN**.
- POSTGRES DURABILITY / CLOUD SECRET RESOLUTION / PRODUCTION SERVICE: **OPEN**.
- CHATGPT CONNECTION / CUTOVER: **NOT PERFORMED**.

Deployment requires exact registered Google `https://gateway-host/google/callback`, separate secret references and funded bounded PostgreSQL, signed-off TLS, correct ChatGPT CIMD callback, Cloud Armor and live one-sided failure-mode checks. Do not treat health 200 or mock tests as real OAuth fruit.

Reference standards: https://developers.openai.com/plugins/build/auth and https://developers.google.com/identity/protocols/oauth2/web-server
