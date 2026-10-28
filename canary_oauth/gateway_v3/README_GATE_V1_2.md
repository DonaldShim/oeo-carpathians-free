# C-Lab OAuth Gateway V1.2 — cumulative security and transport patch

This ZIP retains the full Gateway V1+Gate0 implementation and tests. It adds the `mcp/www_authenticate` metadata challenge to unauthenticated MCP responses, without changing the Google token, database, or upstream semantics, and adds a regression test for fail-closed behavior. Independent local replay: 26/26 tests pass. It records actual public ChatGPT CIMD metadata and a privacy-preserving production Google-client allowlist comparison.

V1.2 is an executable local prototype, NOT a live Google or ChatGPT OAuth deployment. Do not connect to production unless dedicated Postgres and Secret Manager, the registered Google callback, secure token handling, billing and consent are independently certified.

Run `PYTHONPATH=. pytest -q`. Run `python -m gateway.deploy_gate` in an authenticated, authorized GCP CLI for a read-only preflight.
