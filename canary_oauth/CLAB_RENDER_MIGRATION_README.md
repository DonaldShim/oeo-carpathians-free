# C-Lab Render OAuth read-only gateway migration (2026-11-23)

This is an isolated, immutable-source candidate cutover of the **existing** Render Free OAuth Canary service to a strict 5-tool read-only C-Lab MCP.

- Original OAuth Canary branch remains independently pinned at `clab-oauth-canary-pre-migration-rollback-20261123`.
- Existing URL: https://c-lab-oauth-canary-20261025.onrender.com/mcp
- OAuth authorization server is the same existing issuer (Google identity provider, PKCE S256, rotating OAuth refresh tokens).
- New scope: `c_lab_control.read`; **legacy `c_lab_canary.read` cannot read production data**.
- Upstream is pinned to the existing authenticated Render V2.2 snapshot, `CLAB_READONLY_PROXY_TOKEN` in server env.
- OAuth state moves to an isolated database `clab_oauth_gateway_v1` on existing Neon Free, separate restricted role `clab_oauth_gateway_rw`; schema preprovisioned, runtime starts with `CLAB_OAUTH_PREPROVISIONED=1` and no DDL.
- The canonical native GCP endpoint remains broken while its Billing Account is closed. Do not relay compute writes. No VM starts, scientific workloads or metadata writes.
- Allowed tools: `get_control_health`, `get_controller_status`, `get_fabric_health`, `get_snapshot_provenance`, `get_guest_health`; all requests have `arguments={}`.
- Unknown tools, including `compute_submit`, `compute_stage` and `start_vm`, return `-32601`.
- No false green on stale snapshots or proxy failure; no reconnect loop on OAuth storage failure.
- Scope or issuer change requires one genuine owner OAuth login in ChatGPT; preserving existing old Cloud Run tokens would not be secure.
- Stored user data and active auth tokens from the older Render Postgres are **not** copied; new users authenticate in the Neon-backed flow.
- Local synthetic test suite `test_clab_readonly_migration.py`: 14/14 PASS; production E2E and ChatGPT OAuth relink must be confirmed separately.

**Release gate:** do not assert full C-Fabric scientific parity, nor claim full MCP migration completed before Render live OAuth canary and ChatGPT readback. Rollback only the existing Render free OAuth Canary code branch; avoid GCP billing changes.
