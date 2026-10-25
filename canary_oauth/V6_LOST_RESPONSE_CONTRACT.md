# V6 — Lost successful refresh response recovery candidate

## State
- This is a SEPARATE experimental GitHub branch. The live Render V5 branch and canonical C-Lab/C-Fabric are UNCHANGED.
- Opt-in extension: `Idempotency-Key` request header, a fresh client-generated random URL-safe 43–128-character nonce, sent with `grant_type=refresh_token`.
- Server requires `CANARY_REFRESH_RECOVERY_KEY` (independently generated 43+ random chars) to activate **only this extension**. When absent, legacy refresh remains unchanged; providing an idempotency key returns 503.
- On successful refresh, the server commits an AES-GCM encrypted 120-second receipt, bound by AAD to old refresh hash, attempt hash, client ID and MCP resource.
- Exact identical retry can restore the **same** successor token pair, without counting a second refresh success.
- Wrong attempt, missing attempt, tampered ciphertext, revoked family, consumed successor or expired recovery are denied.
- Correct receipt recovery does NOT require Google login; the client must retain the original refresh token and its generated attempt nonce across the failed HTTP request.
- The two-token requirement does **not** make OAuth public bearer tokens sender-constrained; a thief who obtains both may still retry.

## Empirical tests (isolated)
- Existing V5 test suite on this branch: 17/17 PASS with fake Google identity and SQLite.
- Lost-response baseline vs candidate: 20/20 PASS on SQLite, including same successor after dropped reply and 120s timeout/tamper tests.
- DB engine reconstruction using durable local SQLite file: 3/3 PASS.
- Official OpenAI Responses API payload contract: 3/3 PASS (mock client, no paid SDK call).
- No real PostgreSQL concurrency replay of the V6 extension; no real ChatGPT client or cold-token-vault restart.
- The live Render service has NOT been redeployed from this branch. Do not claim the fix is active.

## Deploy gate
1. Independently review the source and absence of secret leaks.
2. Run fixed REAL PostgreSQL transaction/race/restart replay in the existing private canary DB; do not open external IPs.
3. Configure `CANARY_REFRESH_RECOVERY_KEY` only within isolated canary Render environment (never in Git/messages).
4. Deploy in isolated canary after explicit rollback snapshot; verify legacy V5 OAuth and all existing Google PKCE/refresh tests.
5. Test dropped HTTP response on a real client sending same `Idempotency-Key` through an actual HTTPS connection, and verify the exact same successor is returned.
6. Leave canonical C-Lab and scientific jobs untouched.

## Critical impossibility boundary
The standard OAuth public-client retry with only the previous refresh bearer cannot be safely distinguished from an attacker replaying that bearer. Returning the successor for such a request would give it to a thief. Hence the safe recovery requires a second independent client-held attempt secret, sender-constrained credentials, or a separately authenticated session.

ChatGPT's documented OAuth client does not promise to send the custom `Idempotency-Key` for refresh. Therefore this candidate does NOT prove or automatically repair a lost response in ChatGPT's own credential manager.

## Official OpenAI transport
The OpenAI Responses API supports a remote MCP server via `tools:[{type:'mcp', server_url:'...', authorization:current_access_token}]`. This is an official, independently controlled transport; it does NOT connect the user's ChatGPT application account and does not have built-in ownership of the canary refresh token. A local OAuth agent must refresh and supply the current token for EVERY API request.

The existing Plugin Creator can create/inspect package releases but does NOT expose an action to force an end-user ChatGPT OAuth connection. Native ChatGPT refresh remains OPEN pending a supported ChatGPT-side linked connection and actual server-side refresh observation.
