# C-Lab OAuth Canary — independent authorization test

This is an isolated Google OIDC to OAuth2 token broker experiment, *not* a C-Fabric clone.
Its sole MCP tool is a synthetic read-only health response, with no access to C-Lab science.

Default security posture: CANARY_OAUTH_ENABLED=0 and missing secrets make all OAuth and MCP calls return 503.

To enable after code review configure in the Render service only:
- CANARY_OAUTH_ENABLED=1
- CANARY_ISSUER=https://<exact service host>
- GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET
- GOOGLE_ALLOWED_EMAIL (exact approved user)
- DATABASE_URL (isolated PostgreSQL, not any C-Lab database)
- TOKEN_HASH_PEPPER (32+ characters, generated securely)
- METRICS_READ_TOKEN (32+ characters)
Register the Google redirect URI https://<exact host>/google/callback in Google Cloud console.

The ChatGPT OAuth client ID is pre-registered as clab-canary-chatgpt-20261025 with redirect https://chatgpt.com/connector_platform_oauth_redirect.
MCP URL: https://<host>/mcp. Configure a *separate* test plugin in ChatGPT, never replace production.
The user must perform the first Google login and consent. Do not paste credentials or OAuth code into a chat.

Events stored as counters ONLY:
- refresh_token_issued
- refresh_grant_received
- refresh_success
- access_validated

Tokens are random opaque values; only keyed HMAC digests are stored. No token values are logged.
This is an experimental issuer and requires independent security review before any actual credential onboarding.
Public free-tier services may sleep; use only for tests and do not claim uptime or production readiness.

