# C-Lab OAuth Gateway — verified interoperability facts and release gate

Scope: independent Gateway prototype. All values here are nonsecret identifiers or booleans.

## Read-only live observations (2026-10-28)

1. The public, real ChatGPT CIMD `https://chatgpt.com/oauth/client.json` was retrieved over HTTPS using an authorized operator computer. Its `client_id` is exactly that URI. Its `redirect_uris` includes `https://chatgpt.com/connector_platform_oauth_redirect`, `grant_types` includes `authorization_code` and `refresh_token`, and `token_endpoint_auth_methods_supported` includes `none` and `private_key_jwt`.
2. The canonical production Cloud Run service has exactly **one** configured Google OAuth client in `OAUTH_ALLOWED_CLIENT_IDS`, and it equals the **existing** ChatGPT-approved Google client ID whose nonsecret value was independently established in the legacy Host Inspect plugin manifest. Existing production ready revision remains `c-lab-gcp-control-custody-v1-prod-20261020`.
3. This confirms client allowlist compatibility **if and only if** the Gateway uses that existing Google client ID. A newly created Google client requires a separate, reviewable production allowlist change. It does not prove possession of the approved client's confidential secret nor registration of the Gateway's new Google callback.
4. The exact upstream resource is `https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp`. No production route, IAM, or secrets were changed by these read-only observations.

## Newly detected client authorization UI risk

Official plugin OAuth reference specifies tool-level `securitySchemes` metadata and an `_meta["mcp/www_authenticate"]` challenge (with `error` and `error_description`) to trigger linking when a protected tool is invoked. The V1 prototype returned only HTTP `WWW-Authenticate` and an `invalid_token` body. The current additive patch preserves HTTP 401 and also returns the metadata challenge without forwarding unauthenticated calls. Test `test_unauthenticated_mcp_advertises_both_auth_challenges` passes.

References:
- https://developers.openai.com/plugins/build/auth
- https://developers.google.com/identity/protocols/oauth2/web-server

## Non-negotiable remaining obligations

- The current Google web-client secret is **not available** in the Gateway and must never be extracted from active sessions or chat output.
- The Gateway callback `https://<new-service>/google/callback` is **not yet registered** in the Google Auth Platform for any approved web client. No live Google login can legitimately complete without it.
- No dedicated, backed-up PostgreSQL or Gateway-specific Secret Manager versions are confirmed. The existing free Render database belongs to OAuth Canary and expires in November 2026; do not reuse it.
- The private ChatGPT/Codex plugin probe is not a ChatGPT Web connection. Neither real Google post-expiry refresh nor real ChatGPT post-expiry refresh has been run on this Gateway.
- The current GCP billing-link check does not certify active Free Trial credits on **2026-10-28** or guarantee zero card charges. No paid database or Gateway Cloud Run service was created.

Closure: **CIMD_METADATA_COMPATIBILITY=AFFIRMED**, **EXISTING_GOOGLE_CLIENT_ALLOWLIST=AFFIRMED**,
**HTTP_AND_TOOL_LEVEL_AUTH_CHALLENGE=LOCALLY_REPLAYED**, **REAL_END_TO_END_OAUTH=OPEN**.
