# Offline Google OAuth — isolated admission result (2026-10-25)

**Status: OPEN / deployment blocked.** Do not mutate production OAuth or canonical C-Fabric.

## Verified today
- Current personal C-Lab GCP Control plugin v1.0.0: App-backed package exposes `.app.json` and `.codex-plugin/plugin.json`, but **not** `mcp.json` or `.mcp.json`.
- Native `get_control_health({})`: `ok=true`.
- Plugin Creator `update_plugin` explicitly requires preserving App-backed MCP bindings. Thus a package edit cannot be assumed to change production OAuth authorization requests.
- Google documents `access_type=offline` on its authorization request as prerequisite for refresh. The `offline_access` OIDC scope alone does not substitute for it.
- OpenAI documents `authorizationUrl` as an override for traditional MCP plugin manifests. It does **not** guarantee arbitrary query parameters in such overrides are retained by ChatGPT on the wire.
- Locally executed isolated prototype `offline_candidate.py`: 11/11 PASS synthetic. It explicitly refuses the observed `App-backed` production package. ZIP: `C_LAB_PROD_OAUTH_MINIMAL_OFFLINE_CANDIDATE_20261025.zip`; SHA256 `ded3457036c44be27d86424a66029d32e2805ac762cc57bc7390f5af62d29710`.

## Carrier tournament
A. Minimal `authorizationUrl=https://accounts.google.com/o/oauth2/v2/auth?access_type=offline` override. Prototyped but **NOT certified** as supported by actual ChatGPT runtime; current App-backed production manifest cannot be changed via Plugin Creator.
B. Patch existing authoritative Google authorization URL generator to pass `access_type=offline`, preserving client/scopes/callback. **BECOMING**; source owner missing.
C. Replace production issuer with Canary / shadow auth-broker. **REJECTED** as a minimal reversible migration without a separate security contract.

## Required proof for deployment
1. Obtain read-only authoritative OAuth binding configuration from existing production App/Google Cloud control plane, plus live service image/source provenance (no credentials).
2. Locate the **actual** authorization-request generator and determine its supported edit point. If client-owned by ChatGPT and no supported custom query parameters, STOP without modifying Cloud Run.
3. Stage and capture actual Google authorization request (no secret URL output), assert exactly one `access_type=offline`, same approved client/redirect/resource/PKCE.
4. Prove real Google refresh-token issuance with owner consent; then native ChatGPT post-expiry refresh and successful protected C-Lab MCP read with server-side audit.
5. Preserve existing production connection and rollback; no Fabric/scientific changes.

Evidence: https://developers.google.com/identity/protocols/oauth2/web-server and https://developers.openai.com/plugins/build/plugins

**Current result:** generated and tested candidate, **no physical production transfer**.
