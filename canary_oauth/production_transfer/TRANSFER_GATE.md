# Production C-Lab OAuth continuity — exact next executable move

STATUS: **OPEN / AUTHORITATIVE_OAUTH_BUILD_INPUT_ACCESS**. No production deploy or OAuth config change executed.

## Confirmed baseline
- C-Lab GCP Control (personal plugin 1.0.0) is connected. `get_control_health={ok:true}` and `get_fabric_health={ok:true}` readback.
- Production Cloud Run resource `https://c-lab-gcp-control-w7neqnzura-ew.a.run.app`, Google issuer `https://accounts.google.com`, existing scopes `openid email profile` (historical auth contract; verify current revision).
- Separate Canary V9 native ChatGPT refresh was verified, but its custom issuer, token store and resource are **NOT** transferable to Google's production OAuth session.
- Scoped C-Lab Control tools do not currently expose the authoritative production **OAuth layer** source/build input, exact authorization URL parameters or production client refresh evidence. `get_transport_release_provenance(component=publisher_validator)` is for a **different** component and cannot certify OAuth.

## Critical transport distinction
Google returns a refresh token only if the **actual ChatGPT→Google authorization request** includes `access_type=offline` (and reconsent may require `prompt=consent`). Merely patching the Cloud Run MCP server DOES NOT add parameters to the client-generated Google authorization URL if ChatGPT connects directly to Google. Do not change the Cloud Run service until identifying whether the auth configuration lives in ChatGPT plugin configuration, an existing auth layer, or a separate supported authorization-server front-end.

## Permitted gate sequence
1. Via existing authenticated Google Cloud control plane (not RDC), read exact *OAuth/management adapter* service/revision, image digest, source repo+commit or archive hash, OAuth client metadata (NO secrets), source of authorization parameters, token endpoint and protected resource binding.
2. Select smallest existing-surface edit supporting `access_type=offline` without changing production OAuth client, callback URI, scopes, audience, Cloud Run IAM or scientific logic. If ChatGPT plugin cannot express this parameter and there is no existing compatible auth surface, status OPEN — don't introduce a shadow Fabric.
3. Build/test an isolated candidate; Cloud Run code changes require tagged revision at 0% traffic and validated rollback; plugin configuration changes require guarded versioned plugin release and explicit review of existing installed session.
4. Test real Google issuance of refresh without exposing token values, first read, actual expiry, subsequent native ChatGPT refresh grant and protected read. Correlate via session-safe audit; distinguish client attribution limits.
5. Promote only after verified certificates; preserve rollback and reverify C-Fabric health.

## Fail/rollback
No authoritative source => STOP. No real offline support => STOP. Any loss of production tools or oauth protection => rollback. Never mutate canonical C-Fabric, publisher/validator, jobs, IAM, SA keys or science.

Synthetic package tests: 10/10 PASS; real deployment state OPEN (7 gate blockers).
