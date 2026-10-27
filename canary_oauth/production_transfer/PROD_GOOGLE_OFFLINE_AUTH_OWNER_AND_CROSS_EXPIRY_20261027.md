# Production Google OAuth offline request provenance & cross-expiry audit (2026-10-27)

Status: **CERTIFIED DIAGNOSTIC / PRODUCTION REQUEST MUTATION OPEN**. User explicitly authorized change and real refresh replay. **No production OAuth release or connector configuration was mutated** because the relevant authorization parameter is owned by ChatGPT OAuth host and is not exposed via the available App-backed C-Lab plugin API.

## 1. Exact active OAuth authority — observed live

From authorized read-only request on production domain:

- `GET https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/.well-known/oauth-protected-resource` => **HTTP 200**, returned exactly relevant fields:

```json
{
  "authorization_servers":["https://accounts.google.com"],
  "resource":"https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp",
  "resource_name":"C-Lab GCP Control MCP",
  "scopes_supported":["openid","email","profile"],
  "bearer_methods_supported":["header"]
}
```

- `GET /mcp` without bearer => **401** `invalid_token`.
- Google's official `https://accounts.google.com/.well-known/openid-configuration` live response: issuer `https://accounts.google.com`; authorization endpoint `https://accounts.google.com/o/oauth2/v2/auth`; token endpoint `https://oauth2.googleapis.com/token`; `scopes_supported=openid,email,profile`; `grant_types_supported` includes `authorization_code` and `refresh_token`.

**Derived causal result:** ChatGPT is the OAuth client constructing its authorization request directly to Google; the Cloud Run resource only advertises the authorization server and checks Google bearer credentials. Changing Cloud Run environment or adding the V11.1 health alias cannot inject `access_type=offline` into an authorization request built by ChatGPT.

## 2. Platform editor control — inspected

Existing C-Lab GCP Control App-backed plugin: `plugin_asdk_app_6abcc29eafd881919784b9d377ea89cf`, release `PluginRelease_e20286906ea48191b5dc0712f98e7f72`. Plugin Creator `get_plugin_files` yields only `.app.json` and `.codex-plugin/plugin.json`, with App binding + presentation metadata. No `auth`, `authorizationUrl`, `access_type`, `prompt`, `authorizationParams`, or `mcpServers` modification surface exists in these files.

The **update_plugin** API for App-backed plugins explicitly requires preserving App bindings and MCP configuration and only supports updates of skills/support files/version/keywords/onboarding/local-executor. Mutating the auth configuration via that API is **not an authorized capability**.

A separate *legacy* `c-lab-host-inspect-ro` plugin has its own `.mcp.json` with `authorizationServerBase=https://accounts.google.com`, provided Google client, `baseScopes=[openid,email,profile]`, and no extra authorization parameters. This separate plugin cannot configure the App-backed production C-Lab.

Current OpenAI Plugins OAuth configuration reference documents `authorizationUrl`, `tokenUrl`, `authorizationServerBase`, `resource`, `baseScopes`, `defaultScopes`, `oidcEnabled`, etc., but does **not document** a custom authorization-query-parameter override. A supplied `authorizationUrl` with embedded query parameters has NOT been verified as supported by the host and cannot be treated as a certified repair:
https://developers.openai.com/plugins/build/plugins

Google requires `access_type=offline` **in the actual outgoing Google OAuth authorization request**; the `offline_access` scope is **not** a substitute for Google:
https://developers.google.com/identity/protocols/oauth2/web-server
https://developers.google.com/workspace/guides/configure-mcp-servers

## 3. Independent OAuth cross-expiry replay

The **isolated connected C-Lab OAuth Canary** (Render, private user-specific plugin, **not Google production OAuth**) returned valid server-trace evidence before and after its prior access-token expiry.

Earlier read:
- `server_epoch=1793110813`, `access_expires_at=1793110902` (= 2026-10-27T14:21:42Z).
- Session totals `refresh_grant_received=27, refresh_success=27, refresh_token_issued=28, access_validated=8`.

Later authenticated read:
- `server_epoch=1793121747` (= 2026-10-27T17:22:27Z), **3h00m45s after prior expiry**.
- `access_issued_at=1793121746`, `access_expires_at=1793121836`.
- Session totals `refresh_grant_received=29, refresh_success=29, refresh_token_issued=30, access_validated=9`.
- Recent audit shows `refresh_grant_received` then `refresh_success` at epochs `1793121473` and `1793121746`.
- No access or refresh token values inspected or stored.

The paired before/after readings certify working **Canary-only** native refresh across the prior access expiry, followed by successful protected read. They **do not prove Google production refresh**.

In the same later window, canonical production `get_control_health` was `ok=true` at `2026-10-27T17:22:30Z`; `get_fabric_health` also `ok=true` with ingress and runtime HTTP 200. The C-Lab production app read is real but it lacks a session-scoped Google refresh ledger proving a new Google refresh grant.

## 4. Safe production resolution / stop condition

`PRIMARY_BLOCKER = CHATGPT_MANAGED_GOOGLE_OAUTH_AUTHORIZATION_REQUEST_PARAMS_UNEXPOSED`.

The only repair consistent with the requested **same direct Google client, same production resource, no auth migration** is an officially supported way to make ChatGPT include `access_type=offline` in its authorization request, and optionally `prompt=consent` during a consciously reauthorized connection. The current connected App-backed plugin editing tools do not expose that facility. Reconnection/installation requires the user's explicit interaction and must not be invented.

A production cutover requires: (a) exact outbound parameter-presence certificate excluding auth code/state/client secret; (b) fresh true Google `refresh_token_issued=true` event from an authenticating endpoint without disclosing token; (c) a read of an existing C-Lab tool after expiry *attributed to this production Google session's refresh*, not merely any successful read; (d) exact rollback and live C-Fabric health. None of (a)-(c) is yet proven.

**REJECTED carrier:** deploy `V11.1` synthetic image into `c-lab-gcp-control` or update its routing/IAM: it would break genuine OAuth (HTTP 503), access to scientific tools and existing production semantics.

**AFFIRMED:** direct Google authority identified, OAuth host ownership diagnosed, Canary refresh after expiry proven, production C-Lab still healthy.

**OPEN:** Change of ChatGPT OAuth request, Google refresh issuance and attributable Google production post-expiry replay.

No production changes, no scientific jobs, no OAuth secret export, no forced reconnect.
