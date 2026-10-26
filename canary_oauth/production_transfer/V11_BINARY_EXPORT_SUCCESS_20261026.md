# V11 original ZIP — binary export succeeded (2026-10-26)

**BLOCKER ORIGINAL_V11_ARCHIVE_MATERIALIZATION_UNAVAILABLE: RESOLVED for GitHub-backed Codex.**

Repo: `DonaldShim/oeo-carpathians-free`

Branch: `c-lab-oauth-v11-zero-traffic-synthetic-20261025`

Binary path: `canary_oauth/production_transfer/artifacts/C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip`

GitHub blob SHA-1: `1702ad03342a20acc86c40a104ec909a9f63126d`

Original file SHA-256: `d2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1`

Original exact bytes: `14853`, CRC PASS locally. GitHub branch tree readback gave matching git blob SHA and size. The original local git blob hash was computed independently and matched GitHub's blob SHA. No Cloud Run mutation.

## Direct one-shot retrieval in authorized Cloud Shell / Codex

```bash
set -euo pipefail
BRANCH=c-lab-oauth-v11-zero-traffic-synthetic-20261025
REL=canary_oauth/production_transfer/artifacts/C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip
URL="https://raw.githubusercontent.com/DonaldShim/oeo-carpathians-free/${BRANCH}/${REL}"
curl --fail --location --silent --show-error --retry 3 "$URL" -o C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip
printf '%s  %s\n' 'd2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1' 'C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip' | sha256sum -c -
unzip -t C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip
```

If GitHub network or hash verification fails: STOP `BINARY_EXPORT_RETRIEVAL_FAILURE`, no deployment.

**Next target:** stage the *synthetic* V11 into a **separate test-only Cloud Run service** with independent least-privilege identity, non-public invoker policy, immutable image digest and bounded budget. Do not deploy into shared production service: public invoker policy makes its tagged revisions publicly callable even at zero traffic.

Do not claim actual Google OIDC or native ChatGPT OAuth continuity from V11 synthetic smoke tests.
