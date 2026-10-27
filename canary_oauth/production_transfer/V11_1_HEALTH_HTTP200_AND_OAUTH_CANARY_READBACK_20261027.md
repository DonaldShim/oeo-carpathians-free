# V11.1 health successor — live Cloud Run and OAuth scope readback, 2026-10-27

## Build / publication

- Workflow: https://github.com/DonaldShim/oeo-carpathians-free/actions/runs/40516642056
- Commit `1ca3b4daed1504f87c982ee6fc03dffcfd255345`.
- Exact source V11 ZIP SHA-256 `d2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1`.
- Minimal source mutation: insert `@app.get('/health')` directly above the existing `@app.get('/healthz')` decorator, sharing the same function. No real OAuth provider is added.
- CI: 35 tests PASS; build and GHCR push PASS. GHCR public manifest inspected independently, schema 2, 8 layers.
- New immutable image: `ghcr.io/donaldshim/clab-oauth-v11-synthetic@sha256:7cd72ca3a9ae44453316b87efc566903e161323fbc786836ae7978c8f2035de6`.

## Live deployment and isolation

- Existing private test service `c-lab-oauth-v11-test`, region `europe-west1`, project `project-4e9f56f4-a524-4759-91f`.
- New successor revision `c-lab-oauth-v11-test-00002-mod`, tagged `v11health`.
- Tagged URL `https://v11health---c-lab-oauth-v11-test-w7neqnzura-ew.a.run.app`.
- Deployment CLI EXIT 0: "revision ... 00002-mod has been deployed and is serving 0 percent of traffic".
- Independent service readback: old `00001-wqm` revision retains 100% of ordinary test-service traffic; new `00002-mod` only has the tag. Production `c-lab-gcp-control` still on `c-lab-gcp-control-custody-v1-prod-20261020`.
- New deployed image digest and service account independently verified. Test IAM public invoker bindings: zero.

## HTTP replay on exact tagged revision

Authenticated `gcloud run services proxy c-lab-oauth-v11-test --tag=v11health --port=19184`:
- `GET /health` **HTTP 200**, body:
  `{"component":"isolated-oauth-v11","ready":false,"synthetic_only":true,"production_access":false,"science_access":false,"state_durable":false}`.
- `GET /healthz` **HTTP 404** Google Frontend HTML (the original problem remains).
- `GET /authorize` HTTP 503 `{"error":"real_identity_provider_not_configured"}`.
- `GET /.well-known/oauth-authorization-server` HTTP 503 `{"error":"not_configured"}`.
- `GET /mcp` HTTP 405 (GET is not a supported MCP operation).
- Anonymous `GET /health` and `GET /authorize`: **HTTP 403** each.

**Closure:** The requested real Cloud Run `/health` transport HTTP 200 is AFFIRMED, while the application-reported `ready=false` is deliberate for synthetic mode. This is NOT a live Google OAuth provider readiness certificate.

## Separate OAuth Canary actual external readback

A *different*, connected `C-Lab OAuth Canary` read-only tool returned a live session-scoped audit (2026-10-27):
- `component=C-Lab OAuth Canary`, `ok=true`, `science_access=false`.
- `oauth_client_id=https://chatgpt.com/oauth/client.json`, resource `https://c-lab-oauth-canary-20261025.onrender.com/mcp`, scope `offline_access c_lab_canary.read`.
- `session_oauth_audit.source=postgresql_canary_oauth_trace_v8`.
- `refresh_grant_received=25`, `refresh_success=25`, `refresh_token_issued=26`, `access_validated=7` in the **Canary session audit**.
- Public client explicitly records `client_origin_proof=PUBLIC_CLIENT_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED`.
- This constitutes real OAuth refresh behavior for the **external Canary**, not for this new Cloud Run V11.1 image.

Canonical C-Lab control/controller/fabric live health after tests: all `ok=true`, v54-ingress HTTP 200, fabric-runtime HTTP 200, 2026-10-27T14:18:05–06Z.

## Remaining proof obligations

- V11.1 Cloud Run code still returns `ready=false`, lacks real identity provider and durable token/session storage; does not implement or demonstrate actual Google OAuth authorization/refresh.
- Reusing public-client Canary results as a certificate for V11.1 would be incorrect. No production OAuth keys, refresh tokens, ChatGPT connector config or C-Fabric permissions should be copied into this test.
- To attempt true OAuth integration next, first define a separate opt-in test client with explicit issuer, redirect/callback registration, secure token transport, refresh persistence and replayable session log; verify the source of each credential without exporting secrets. Deployment and any redirect/allowlist changes require distinct gated rollout and rollback.
- No production OAuth cutover and no science jobs were performed.
