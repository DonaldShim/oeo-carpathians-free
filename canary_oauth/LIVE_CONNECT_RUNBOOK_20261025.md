# C-Lab OAuth Canary — safe cutover handoff (25 Oct 2026)

## Assets physically created

- Canary (Render): https://c-lab-oauth-canary-20261025.onrender.com
- Render service ID: `srv-dbeqvffavr4c73br46cg`
- Render dashboard: https://dashboard.render.com/web/srv-dbeqvffavr4c73br46cg
- Isolated Postgres: `dpg-dber2krncjis73f5muh0-a`, Frankfurt, free, expiry 2026-11-24; **external IP allowlist empty by design**.
- Database dashboard: https://dashboard.render.com/d/dpg-dber2krncjis73f5muh0-a
- GitHub branch: `c-lab-oauth-canary-20261025`; production main branch untouched.
- Cloud config: `CANARY_ISSUER=https://c-lab-oauth-canary-20261025.onrender.com`; `CANARY_OAUTH_ENABLED=0`; autoDeploy off.
- Latest tested code commit: `ea68d564e8200a7e06843ff4c39ca4288a604d73`.
- Live integration: 17/17 (with signed fake Google ID token, SQLite in-memory) and public fail-closed 6/6.
- Refresh event counters in isolated database: `refresh_token_issued`, `refresh_grant_received`, `refresh_success`. The first counter increments on both initial grant and each rotation.

## Why live Google login is still blocked

Real Google OAuth credentials and consent are not available to this automated chat. The Render plugin intentionally hides Postgres connection credentials, and Render's read-only query tool cannot access the DB with the intentional empty external allowlist. Neither limitation should be bypassed by leaking secrets or exposing the database.

**Do not switch `CANARY_OAUTH_ENABLED` to 1 until every required variable is set, an independent code/security review is completed and the Google consent screen is configured.**

## Exact, minimal owner actions (in browser, with values never pasted into ChatGPT)

1. Google Cloud Console -> Google Auth platform -> Clients -> Create client -> **Web application** for this **canary only**. Authorized redirect URI must be exactly:
   `https://c-lab-oauth-canary-20261025.onrender.com/google/callback`.
   Configure user type/testing consent and authorized test account. This client is different from ChatGPT's OAuth client registered with the canary.
2. Render database dashboard -> Connect -> copy the **internal** connection string. It is reachable over the Render private network, with no public allowlist opening.
3. Render service dashboard -> Environment -> configure the following secrets there, **not in messages / Git / .env committed to Git**:
   - `GOOGLE_OAUTH_CLIENT_ID` = the separate Google Web application client ID.
   - `GOOGLE_OAUTH_CLIENT_SECRET` = its secret.
   - `GOOGLE_ALLOWED_EMAIL` = exact test account email.
   - `DATABASE_URL` = internal connection string from the canary DB page.
   - `TOKEN_HASH_PEPPER` = cryptographically random, length 32+; generate locally and store in Render only.
   - `METRICS_READ_TOKEN` = independent random 32+ secret for metrics read endpoint.
   - Keep `CANARY_ISSUER` exactly the HTTPS issuer above.
   - Finally, after independent review, switch `CANARY_OAUTH_ENABLED=1` and deploy. Do **not** reuse production C-Lab credentials.
4. Verify `GET /healthz` now reports `ready:true`; verify OAuth discovery and no unauthenticated token issuance. On failure, set `CANARY_OAUTH_ENABLED=0` and redeploy (rollback).
5. From ChatGPT web **create a separate custom MCP plugin**, server URL `https://c-lab-oauth-canary-20261025.onrender.com/mcp`, OAuth authentication. Register the **preconfigured public client ID** `clab-canary-chatgpt-20261025`, no client secret. Expect ChatGPT redirect `https://chatgpt.com/connector_platform_oauth_redirect`. Keep existing canonical C-Lab plugin unchanged. Verify actual ChatGPT builder-selected callback URL before test; this canary has only the stable URI allowed.
6. A human user must authorize once through the Google consent UI. Neither the broker nor the assistant can authorize silently for them.
7. After ChatGPT first calls `canary_control_health`, read **aggregate** counters in the Render PostgreSQL dashboard (internal query, no token fields):
   `SELECT name,total FROM canary_event ORDER BY name;`
   With a 90-second canary access-token lifetime, test another ChatGPT read after expiry, without manually reconnecting. Require `refresh_grant_received` and `refresh_success` to increase, and a subsequent authenticated read to succeed. A raw successful read alone is not proof.
8. Negative tests: wrong PKCE, wrong resource/audience, expired token, revoked refresh family, concurrent refresh, cross-client identity, Google consent failure and fallback/rollback. Do not ship before these pass under real Postgres and ChatGPT.

## Security and limits

- Only one synthetic read-only MCP tool; **no C-Fabric scientific permissions**.
- Token values must never appear in the app logs, report files, Git commits or conversations. Hashed HMAC identifiers only in database.
- Render edge/provider logging of OAuth authorization codes is a separate platform-level logging risk; verify privacy and retention before real users.
- Refresh race within 3 seconds rejects duplicates but doesn't return an idempotent replacement token. Concurrency and retry behavior with ChatGPT is **OPEN**.
- Free PostgreSQL expires 24 November 2026 and is not a production durability/backup guarantee.
- If Google is used only to validate initial identity, it does **not** need a Google refresh token. The C-Lab broker issues its own rotating tokens.
- Fully automatic reconnect/refresh is **OPEN** until real ChatGPT-side end-to-end observation.
