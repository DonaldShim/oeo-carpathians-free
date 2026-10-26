# V11 GHCR publication receipt — 2026-10-26

**Status: GHCR_PUSH=AFFIRMED / ANONYMOUS_PULL=OPEN / CLOUD_RUN_DEPLOYMENT=OPEN.**

Exact user-approved source:
`canary_oauth/production_transfer/artifacts/C_LAB_OAUTH_V11_ZERO_TRAFFIC_CANDIDATE_20261025.zip`
SHA-256 `d2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1`.

Workflow committed at `fdc16b48bbd2aec28faf7e1d10161ca7c75675e9`;
GitHub Actions run [40397927273](https://github.com/DonaldShim/oeo-carpathians-free/actions/runs/40397927273)
completed `success`, 2026-10-26T20:42:31Z.
Workflow: SHA verify PASS; archive member/CRC gate PASS; 32/32 pytest PASS; Docker build PASS; GHCR push PASS.

Image: `ghcr.io/donaldshim/clab-oauth-v11-synthetic:sha-fdc16b48bbd2aec28faf7e1d10161ca7c75675e9`.
Pushed digest: `sha256:a2e28d9c746073b9455c0a75e03bcf2892f3b0bf8339d5990759da27121b9d64`.
No production image, Google credentials, C-Fabric permissions, or scientific files were included in the Docker context; only `app.py` and `requirements.txt`.

## Remaining visibility gate

The GitHub workflow proved authenticated push but **does not prove public package visibility**. GitHub personal Container Registry packages can default to private. No GitHub package-visibility mutation interface is available from this chat; do not claim `GHCR_PUBLIC=true` yet.

Owner-approved public image must be independently checked by an **anonymous pull**, e.g. in Google Cloud Shell:

```bash
TMP_CONFIG=$(mktemp -d)
DOCKER_CONFIG="$TMP_CONFIG" docker manifest inspect \
 ghcr.io/donaldshim/clab-oauth-v11-synthetic@sha256:a2e28d9c746073b9455c0a75e03bcf2892f3b0bf8339d5990759da27121b9d64 \
 >/dev/null && echo GHCR_ANONYMOUS_PULL=PASS
rm -rf "$TMP_CONFIG"
```

If it fails due to authentication, the owner should open GitHub user `DonaldShim` → Packages → `clab-oauth-v11-synthetic` → Package settings → Change visibility → Public. **This change is irreversible** according to GitHub Docs, and it was specifically authorized by the user for this synthetic image only. Retest anonymous pull; record an actual PASS or remain OPEN.

Cloud Run public GHCR image deployment requires a separately scoped test-only SA, a private test service and verified no-extra-charge allowance. Do not modify `c-lab-gcp-control` or create scientific jobs; public GHCR alone does not certify Google OIDC nor native ChatGPT refresh.
