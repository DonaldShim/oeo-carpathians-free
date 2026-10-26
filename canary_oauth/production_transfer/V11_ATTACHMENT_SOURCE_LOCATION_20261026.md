# V11 candidate attachment locator (2026-10-26)

**This branch currently stores the V11 execution report, not the candidate source files.** Do NOT mistake it for a cloneable complete source tree.

The original V11 candidate archive was uploaded to the ChatGPT conversation and verified as a mounted file in the current conversation container:

`/mnt/data/C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip`

Exact SHA-256:
`d2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1`

Contents:
`app.py`, `test_app.py`, `cloudrun_gate.py`, `test_cloudrun_gate.py`, `requirements.txt`, `Dockerfile`, `README_RU.md`, `CLOUD_RUN_STAGE_EVIDENCE.json`, `CERTIFICATE.json`, `SHA256_MANIFEST.json`. ZIP test=PASS.

Note: this sandbox mount is NOT automatically visible from a separate Windows Codex process or Google Cloud Shell. When absent there, use the original ChatGPT conversation attachment via its supported Files/Work materialization workflow. Do not invent any Windows `S:\` path or claim that an inaccessible archive has been read.

Do not deploy the previous candidate as production OAuth. Cloud Run canary must have separate restricted identity, immutable image digest, test-only secret, tagged 0% traffic and verifiable rollback.
