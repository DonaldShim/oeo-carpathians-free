# Supported ChatGPT OAuth authorizationUrl override — candidate plugin, 2026-10-27

## Actual executed admission result

Plugin Creator created a new separate **PRIVATE** personal plugin. The publication and an independent `get_plugin_files` readback succeeded.

- Plugin: `c-lab-google-offline-auth-probe-20261027`
- Backend ID: `plugins_6ae0e241192081918384d0adb5d985fd`
- Version: `0.1.0`
- Current release: `pluginrel_6ae0e2429fd481918ec74ee18bec16ab`
- URL: https://chatgpt.com/plugins/plugins_6ae0e241192081918384d0adb5d985fd
- Portable Plugin package SHA-256: `000653001e3ce5db34e43f23e4b159c1e12a2835d1464baf45f7dd82ea8ba880`.

This private plugin's `mcp.json` was accepted against `https://agent-plugins.org/schemas/1.0.0/mcp.schema.json`. Independent release readback verified the following relevant fields were **retained**:

```json
{
  "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?access_type=offline",
  "tokenUrl": "https://oauth2.googleapis.com/token",
  "authorizationServerBase": "https://accounts.google.com",
  "client": {"mode":"provided", "tokenEndpointAuthMethod":"client_secret_post"},
  "baseScopes":["openid","email","profile"],
  "oidcEnabled":true
}
```

The existing approved **public** Google OAuth client ID is present in the actual package but is not recorded again in this diagnosis. **No client secret or access/refresh tokens were embedded.**

For minimal risk the plugin points only to the already existing **read-only Host Inspect** tagged MCP endpoint:
`https://host-inspect-ro-20261019---c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp`.

**No production App-backed plugin, production Cloud Run routing, IAM, science job, or C-Fabric artifact was modified.**

## Precise admission scope / gap

The supported **`authorizationUrl` endpoint override** is documented here:
https://developers.openai.com/plugins/build/plugins

The plugin **package parser and current release preserve the URL query**. This is **not** yet a certificate that ChatGPT's OAuth runtime will preserve `access_type=offline` when dynamically appending `response_type`, `redirect_uri`, `resource`, `state`, `scope`, `client_id`, and `code_challenge`.

**Next executable external gate requires the user to install/connect the separate private plugin and complete Google OAuth consent.** Plugin installation/connection requires explicit user action. In the outbound redirect, report only **whether the parameter key/value `access_type=offline` is present**; do not share any full URL with state, code, or secrets. If retained, verify a genuine Google refresh grant and protected MCP read after expiry with attributable provider-side audit, not merely successful access.

The existing direct Google OAuth production App-backed connection cannot be updated by this separate plugin's manifest; even full success here would require a versioned native migration plan, not an automatic production cutover.

If the runtime strips the query or refuses the flow, **reject this override carrier**, and initiate a separately certified OAuth 2.1 bridge with its own issuer/resource metadata, CIMD or DCR, S256 PKCE, RFC 9207 issuer identification, Google OAuth offline consent, validation and durable encrypted token/refresh rotation storage, fixed-upstream token forwarding, exact resource/audience controls, and recovery/rollback plan. Do not repurpose the synthetic V11.1 as that bridge.

## Verified statuses

- `PLUGIN_PACKAGE_ACCEPTED = AFFIRMED`
- `AUTHORIZATION_URL_QUERY_RETAINED_IN_RELEASE = AFFIRMED`
- `CHATGPT_OUTBOUND_GOOGLE_AUTH_URL_HAS_ACCESS_TYPE_OFFLINE = OPEN`
- `GOOGLE_REFRESH_TOKEN_GRANTED = OPEN`
- `POST_EXPIRY_PRODUCTION_C_LAB_READ_ATTRIBUTABLE_TO_GOOGLE_REFRESH = OPEN`
- `PRODUCTION_CUTOVER = NOT_PERFORMED`.
