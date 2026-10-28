# Security & proof contract, V1

**No real credentials are present in this package.**

- External redirect invariant: only exact allowlisted ChatGPT callback; Google callback fixed to same Gateway HTTPS origin.
- Client identity: only fixed CIMD URL; this is not proof that a particular installed ChatGPT app uses it. Production metadata must be compared with actual host metadata.
- `access_type=offline` is set ONLY in Gateway→Google authorization request; gateway refresh endpoint uses OAuth2 form & one-use rotation.
- Google `id_token`: signature and issuer/audience/nonce verification is delegated to `google-auth`; test double does not replace live Google OIDC testing.
- Google token handling: encrypted at rest under Fernet; encrypted key and DB credential from Secret Manager; grant invalidates on refreshing reused gateway token.
- Proxy: only three zero-argument, read-only MCP calls; server emits JSON-RPC, never exposes arbitrary upstream methods or URLs.
- Failure cone: Google never issues refresh, unknown caller, expired/replayed code, wrong resource/redirect/PKCE, unexpected body, storage missing => fail closed.
- PostgreSQL transaction row locks protect token rotation; SQLite in tests is not a concurrency proof.
- No cloud deployment or Google OAuth client registration in this build. Production OAuth cutover excluded.

## Residuals

1. Google Web Client registered callback and secret not yet provided via secure cloud secret store.
2. Durable PostgreSQL not yet verified.
3. Google access token acceptance at canonical C-Lab upstream not proven.
4. ChatGPT CIMD discovery, redirect admission, `refresh_token` issuance, native post-expiry replay not tested live.
5. Rate limiting, revocation API, token/key rotation, robust multi-instance persistence/backup drills, encrypted session audit export, Cloud Armor, external penetration review not closed.
6. The OAuth system is not a drop-in replacement for current production C-Lab plugin; explicit app auth migration required.

These are material deploy gates, not cosmetic TODOs. The gateway must remain not production-ready until external readbacks close them.
