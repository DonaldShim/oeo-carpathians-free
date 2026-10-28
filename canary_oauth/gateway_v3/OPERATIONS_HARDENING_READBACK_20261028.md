# C-Lab Gateway V3 — permanent operations gate (2026-10-28 UTC)

## Deployed watchdog
- Default branch GitHub Actions: [c-lab-oauth-gateway-watch.yml](../../.github/workflows/c-lab-oauth-gateway-watch.yml)
- Runs at minutes 8,25,42,59 UTC every hour, with 3 attempts and bounded alerts via GitHub Issues.
- Public probe: [ops/c_lab_gateway_watch.py](../../ops/c_lab_gateway_watch.py); tests: [tests/test_c_lab_gateway_watch.py](../../tests/test_c_lab_gateway_watch.py).
- First real GitHub push-triggered run [40721210068](https://github.com/DonaldShim/oeo-carpathians-free/actions/runs/40721210068) succeeded (7/7 monitor unit tests + live credential-free public-health probe).
- Also verified native connected `C_Lab_OAuth_Gateway_V3.get_control_health` and `get_fabric_health` 2026-10-28 15:59 UTC: healthy.

## Operating invariants
- Gateway Cloud Run separate service `c-lab-oauth-gateway-v3`, ready revision `c-lab-oauth-gateway-v3-httpfix0574`.
- Pinned digest `sha256:f88b6f09628d14efee1c6c7a0697c7db1785c47e41d73ba4990709a75d47204c`.
- Canonical C-Lab separate revision `c-lab-gcp-control-custody-v1-prod-20261020` at 100% canonical traffic, unchanged.
- Automated probe does **not** read OAuth tokens, refresh tokens, cookies, Google credentials, or Firestore documents, and cannot mutate C-Lab. It verifies /health ready, both OAuth discovery endpoints, and unauthenticated /mcp 401.
- GitHub Actions schedule can be delayed or disabled, so no absolute 24/7 SLO is certified.

## Backups: exact limits
- Private Drive folder: https://drive.google.com/drive/folders/1nvWdPEWl8_Gi2B5xrnaZ1osNpeAq2Jt8
- Last physically verified encrypted **real-grant metadata** backup: 2026-10-28T14:38:57Z. Separate synthetic restore test archive exists.
- Prior actual Drive backup/download SHA and **revoked-only** isolated restore are proven by V3 certificates.
- **UNATTENDED DRIVE BACKUP IS OPEN**: personal Drive delegated `drive.file` OAuth not configured on Cloud Run. Do not treat daily health monitor as a backup process; it alerts on backup staleness after 48 hours. Drive service account cannot simply own files in user's personal My Drive.
- Restored metadata is forcibly revoked and requires new consent. Never resurrect old access or refresh tokens from backup. Firestore is authoritative and live sessions cannot be reconstructed from these archives.

## Recovery and cost gate
- On failure compare gateway service revision/digest/secret references and Firestore health; investigate sanitized errors. Do not touch canonical C-Lab.
- Roll back the **Gateway service alone** to known-good digest only after schema and secret reference checks. An older fail-closed revision is not a working rollback.
- After disruptive change, require real native ChatGPT and Google post-expiry refresh readbacks again.
- Cloud Run min0/max1 and Firestore freeTier confirmed, but no claim of $0 future costs. Review linked billing/remaining Free Trial before previously observed 2026-12-17 expiry.
- No production cutover, credentials export, scientific job, or C-Fabric write occurred in operational-hardening steps.

**Closure:** Public watch AFFIRMED; both original real refresh replays AFFIRMED; runtime-independent unattended Drive backups OPEN; post-trial cost and disaster recovery assurance OPEN.
