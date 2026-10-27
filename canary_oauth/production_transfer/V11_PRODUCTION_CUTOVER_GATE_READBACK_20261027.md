# C-Lab production OAuth cutover — live gate readback, 27 October 2026

## Scope and decision

**User requested production cutover. Read-only live preflight executed via authorized RDC (MeAnDeR) with authenticated Google Cloud SDK and connected C-Lab/Plugin Creator tools.**

**Production cutover remains NOT EXECUTED — mandatory Gate 0 / Gate 2 failed due to carrier mismatch and absent authoritative authorization request control.** Do not construe this as user refusal or inaccessible Cloud SDK; authenticated production read access is working.

## Real authoritative production baseline

- Project `project-4e9f56f4-a524-4759-91f`; region `europe-west1`.
- Service `c-lab-gcp-control`, URL `https://c-lab-gcp-control-w7neqnzura-ew.a.run.app`.
- Ready 100%-routed production revision `c-lab-gcp-control-custody-v1-prod-20261020` (created 2026-10-20T19:53:23.010989Z), `Ready=True`.
- Production image `europe-west1-docker.pkg.dev/project-4e9f56f4-a524-4759-91f/c-lab-release/c-lab-gcp-control@sha256:8e0ada2e7592e46d03978eea9ef77a9bc39a78868b81f642fc5f1460e62e2017`.
- Production identity `c-lab-control-mcp@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com`.
- Production container environment **NAMES ONLY, values withheld**: `C_FABRIC_RELEASE_SHA256,OAUTH_ALLOWED_CLIENT_IDS,OAUTH_ALLOWED_EMAILS,UPSTREAM,RELEASE_BROKER_URL,COMPUTE_WRITES_ENABLED,CLAB_OPERATOR_SERVICE_CANARY`.
- Readback live `get_control_health.ok=true`, `get_controller_status.ok=true`, `get_fabric_health.ok=true`, `v54-ingress=200`, `fabric-runtime=200` at 2026-10-27T14:20 UTC.
- Billing project linked to already verified active Free Trial account; never change billing tier.

## Existing connector control surface

Plugin Creator lists editable personal App-backed `C-Lab GCP Control`, backend ID `plugin_asdk_app_6abcc29eafd881919784b9d377ea89cf`, current release `PluginRelease_e20286906ea48191b5dc0712f98e7f72`, version 1.0.0.

`get_plugin_files` shows ONLY `.app.json` and `.codex-plugin/plugin.json` for this App-backed plugin. These manifest files reference a platform App SDK ID and presentation metadata, **not the OAuth authorization request parameters or source.** No verified supported `access_type` override found in these plugin files. A separate historical `c-lab-host-inspect-ro` legacy manifest points to Google `authorizationServerBase=https://accounts.google.com`, with `openid email profile` scopes and approved Google client mode; it also exposes no per-request offline parameter.

Do not modify `.app.json` or fabricate undocumented OAuth fields in the expectation of affecting platform-held authentication.

## Why V11.1 cannot serve production

- Private test service `c-lab-oauth-v11-test`, image `ghcr.io/donaldshim/clab-oauth-v11-synthetic@sha256:7cd72ca3a9ae44453316b87efc566903e161323fbc786836ae7978c8f2035de6`.
- Tagged new revision `c-lab-oauth-v11-test-00002-mod` with `v11health`; 0% untagged traffic, old test `00001-wqm` 100%; **this is not a production revision**.
- `GET /health` via authenticated proxy HTTP 200 but app reports `ready=false`, `synthetic_only=true`, `production_access=false`, `science_access=false`, `state_durable=false`.
- Actual `GET /authorize` HTTP 503 `real_identity_provider_not_configured`; actual discovery endpoint HTTP 503 `not_configured`. V11.1 has NO Google identity provider, NO supported production MCP tool set, NO durable token store, NO production C-Fabric access. Diverting ChatGPT/C-Lab production to this service would cause a predictable functional outage.
- Separate external C-Lab OAuth Canary *has* native ChatGPT OAuth refresh evidence, but scopes are `offline_access c_lab_canary.read`, resource is separate Render Canary, and science_access=false. Counts and token issuance from Canary do **not** certify Google refresh in production.

## Exact unresolved cutover condition

Google's official OAuth web-server documentation: `access_type=offline` must be present in the **original authorization redirect/request to Google's authorization endpoint** to request refresh tokens. Adding a Cloud Run environment variable, switching service images, or changing the MCP protected-resource server alone does not add this parameter if ChatGPT itself constructs the Google authorization URL.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server

Required live observations before a safe cutover:
1. Authoritative owner of Google authorization URL construction (the connected ChatGPT app OAuth config, existing production auth gateway, or valid supported API). Obtain a **sanitized query-parameter key readback**: `access_type=offline` required, `prompt=consent` only where reauthorization is needed. Never log redirect `code`, token, client_secret, state, user email, or authorization URL.
2. Verified minimal supported release/setting changes **inside that owner**, preserving production Google client, callback URI, scopes, issuer and MCP resource identity.
3. Non-prod controlled proof of real Google code exchange with `refresh_token_issued=true`, fresh access token after expiry, and actual ChatGPT MCP read without relinking; existing Canary alone is not sufficient.
4. Read-only before/after release diff, rollback to exact version, matched service traffic and C-Fabric health.
5. Only then production plugin/auth release and guarded production cutover. Never promote V11.1 synthetic image.

### Closure

- Built/run: V11.1 real private tagged service; 35/35 CI tests; real health 200 and private IAM 403.
- Production read: AFFIRMED and healthy.
- OAuth state: Google offline parameter control UNKNOWN; Google production refresh certificate OPEN.
- **Cutover: NOT DONE, certified blocker `AUTHORITATIVE_CHATGPT_GOOGLE_AUTHORIZATION_PARAMETER_CONTROL` and `PRODUCTION_CARRIER_MISMATCH`.**
- No production traffic/IAM/service or OAuth plugin settings changed by this audit; no scientific jobs.
