# C-Lab OAuth Refresh Canary — 25 Oct 2026 operative state

## Physical state (replayed)

- Dedicated Render Web Service: `srv-dbeqvffavr4c73br46cg` at https://c-lab-oauth-canary-20261025.onrender.com
- Dedicated free Render PostgreSQL: `dpg-dber2krncjis73f5muh0-a`, Frankfurt, available; expires 2026-11-24. External IP allowlist remains empty.
- Source: branch `c-lab-oauth-canary-20261025`, revision `c2d4134cf9de3cd5206ec93feccd06de948817d7`.
- ChatGPT private personal plugin created: https://chatgpt.com/plugins/plugins_6addb6f24f748191af8cebdecf98f674, id `plugins_6addb6f24f748191af8cebdecf98f674`, version 0.1.0.
- Exact standalone OAuth client ID preconfigured: `clab-canary-chatgpt-20261025` (public client, `tokenEndpointAuthMethod=none`).
- MCP endpoint `https://c-lab-oauth-canary-20261025.onrender.com/mcp`. OAuth issuer exact `https://c-lab-oauth-canary-20261025.onrender.com`, scopes `c_lab_canary.read offline_access`.
- Canary generated its own fresh `TOKEN_HASH_PEPPER` and separate `METRICS_READ_TOKEN` using OS cryptographic RNG; configured directly as Render environment variables, no values included in this file.
- `CANARY_ISSUER` already configured and `GOOGLE_ALLOWED_EMAIL` bound to the account independently verified to match Render workspace owner and active Google Cloud CLI account; email not disclosed here.
- Explicit `CANARY_OAUTH_ENABLED=0` and `/healthz` ready=false; don't enable prematurely.
- Google Web OAuth client ID/secret for **this separate issuer**: NOT CREATED. Never reuse a production OAuth client secret or store it in Git.
- `DATABASE_URL` to Render canary Postgres: NOT CONFIGURED. Render MCP limits prevent retrieving the internal connection string, with DB external IP allowlist deliberately empty. Never open public database networking just for this test.
- Plugin is **created** but not asserted installed/connected/authorized. Login/consent by real user remains pending.
- Local `S:\C_AGI_RECOVERY\canary_oauth_test_source\canary_oauth\test_isolated_e2e.py` on MeAnDeR performed **17/17** isolated integration checks with locally-signed fake Google ID token and SQLite in-memory. Genuine Google OAuth/ChatGPT use not verified.
- Public HTTPS canary **6/6** checks including correct metadata and rejection of auth/token/MCP while disabled (prior readback); repeat after env updates.
- Canonical C-Lab GCP Control `get_control_health` remained `ok=true` during work; no production mutations and no scientific jobs.

## Secure pending actions

1. Create separate Google Auth Platform *Web application* OAuth client, redirect URL exactly `https://c-lab-oauth-canary-20261025.onrender.com/google/callback`; add the approved test identity. This is a real Google user OAuth client, **not** `gcloud iam oauth-clients` (that creates Workforce Identity Federation/IAP clients).
2. In Render Dashboard configure `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and `DATABASE_URL` for this isolated canary, values only via the Render secrets UI. `DATABASE_URL` must be the Render Postgres **internal** URL, with no external IP allowlisting.
3. Conduct independent security review and readiness check; only then set `CANARY_OAUTH_ENABLED=1`. Do not attach the canonical C-Fabric to this canary.
4. Install the already created PRIVATE plugin in ChatGPT, perform Google consent once. Values of OAuth codes/access/refresh tokens must never go into prompts, files, browser extension logs, or GitHub.
5. Following sign-in perform `canary_control_health`; after the 90-second access-token expiry perform another real ChatGPT read without reconnect. Verify `refresh_grant_received>0` and `refresh_success>0` in canary's protected counters; compare before vs after. Distinguish real refresh evidence from mere successful reads.
6. Adversarial negative cases, real Postgres concurrency/atomicity, client retries, revocation, restart recovery, Google OIDC validation, issuance audit and rollback before claiming end-to-end.
7. Keep free Postgres 30-day expiry and no backups in mind; never call the canary a production-grade authorization service.

## Status

AFFIRMED: Dedicated isolated hosting, 17/17 synthetic-source integration, 6/6 public fail-closed, private plugin creation, two server-only secrets.
BECOMING: Google-to-canary authorization and persistent Postgres wiring.
OPEN: Real Google consent, real ChatGPT refresh grant, uninterrupted multi-session connectivity.
No direct capability for ChatGPT chat-mode Browser to click Google/Render identity UIs; a user Work-mode cloud browser or explicit user UI action is required.
