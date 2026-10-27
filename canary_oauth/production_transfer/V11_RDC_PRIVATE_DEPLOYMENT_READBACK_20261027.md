# V11 private Cloud Run deployment — independently reconciled live readback (2026-10-27)

## Scoped result

**AFFIRMED: A real, isolated, private synthetic OAuth V11 Cloud Run service was created and is Ready.**

This is NOT a native Google OAuth continuity certificate, NOT a production OAuth cutover, and NOT a canonical C-Fabric change.

- Google Cloud project: `project-4e9f56f4-a524-4759-91f`
- Region: `europe-west1`
- Test service: `c-lab-oauth-v11-test`
- **Ready revision**: `c-lab-oauth-v11-test-00001-wqm`
- **Ready condition:** `True`, recorded at `2026-10-27T13:12:37.656663Z`
- Only test-service traffic: **100% to its first revision**.
- Test service URL: `https://c-lab-oauth-v11-test-w7neqnzura-ew.a.run.app` (IAM-protected).
- Service identity: `clab-oauth-v11-test@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com`
- Image: `ghcr.io/donaldshim/clab-oauth-v11-synthetic@sha256:a2e28d9c746073b9455c0a75e03bcf2892f3b0bf8339d5990759da27121b9d64`
- Source ZIP SHA-256 verified again on authorized MeAnDeR PC: `d2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1`.
- Anonymous GHCR manifest inspection: `exit=0`, schema 2, 8 layers.

## Financial and IAM admission

- Owner Google Billing UI, **2026-10-27**: `Free trial account`, ~$198.88 credits left, ends **2026-12-17**, October net payable $0 at screenshot time.
- Live `gcloud billing projects describe`: `billingEnabled=true`; exact link `billingAccounts/01117F-2FB3E2-31D263`. Billing API alone does NOT prove continuing Free Trial mode; dated operator evidence is required.
- Two similar but distinct test service accounts existed. The selected one is the exact `clab-oauth-v11-test@...` identity; the other is `c-lab-oauth-v11-test@...`. They were NOT deleted or modified.
- Checked project and organization `366675516572` IAM policies: no direct role bindings for selected test identity. Separate test identity not used by previously listed services.
- Service IAM readback: **no `allUsers` or `allAuthenticatedUsers` Invoker**. `ingress=all` does NOT mean unauthenticated access, and testing confirmed a private route.
- Production service remains `c-lab-gcp-control` with ready revision `c-lab-gcp-control-custody-v1-prod-20261020`; no production traffic release was performed.

## Real HTTP and Cloud Logging replay

Using authorized Windows Google Cloud SDK via RDC, with a subsequently installed `cloud-run-proxy` component:

| Route / client | Observed result |
| --- | --- |
| Anonymous GET `/` | HTTP **403** |
| Authorized Cloud Run proxy GET `/` | HTTP **404**, FastAPI JSON `{"detail":"Not Found"}` |
| Anonymous GET `/authorize` | HTTP **403** |
| Authorized proxy GET `/authorize` | HTTP **503**, `{"error":"real_identity_provider_not_configured"}` |
| Anonymous GET `/healthz/` | HTTP **403** |
| Authorized proxy GET `/healthz/` | HTTP **307** (FastAPI trailing slash redirect) |
| GET `/healthz`, including authenticated proxy | HTTP **404**, *Google Frontend HTML*, not FastAPI |

Cloud Logging independently displayed request statuses **403, 503, 404, 307, 405** on revision `c-lab-oauth-v11-test-00001-wqm`, 2026-10-27 ~13:20–13:22 UTC.

**Residual OPEN:** exact `/healthz` is intercepted or misrouted at Google Frontend, so the health endpoint lacks successful HTTPS evidence. Real Google OIDC, ChatGPT native refresh, provider tokens, production cutover and long-run concurrency are **OPEN**. The synthetic `/authorize` 503 is expected fail-closed behavior.

## Reconciliation and rollback

The original `gcloud run deploy --no-traffic` attempt failed before creation: the CLI says **`--no-traffic not supported when creating a new service`**. A new private service must initially route 100% **of its own** traffic; this does NOT shift any traffic from production.

The second deployment command created the service. Its PowerShell wrapper suffered a local **case-insensitive variable collision** (`$Target` string overwritten by `$target` Cloud Run object), causing a **false postflight STOP** and a failed automated rollback. This was reconciled independently using fresh `gcloud run services describe`, `get-iam-policy`, actual HTTP requests, and Cloud Logging. No unauthorized service deletion took place. **Do not replay the old wrappers**; service is already deployed.

Dedicated rollback script: [rollback_v11_private_only.ps1](./rollback_v11_private_only.ps1). It is read-only by default. Local syntax test PASS; actual no-delete run returned **`ROLLBACK_PREPARED EXECUTE=False DELETED=False`**. Exact original Windows file SHA256: `f2e5f3ba3aa54bf387ce36320724c41c58e7aa096b29042beab076fcbf84c06f`. **Rollback DELETE not exercised**; do not claim rollback replay PASS.

The prior [v11_free_trial_private_deploy.py](./v11_free_trial_private_deploy.py) retains an invalid `--no-traffic` new-service assumption and must not be re-executed for this already deployed target. The old `DEPLOYMENT_READBACK.json` with STOP records the wrapper failure, not the now independently established Cloud Run deployed state.

Final health readback **2026-10-27T13:25:04–05Z** via canonical C-Lab GCP Control: `get_control_health.ok=true`, `get_controller_status.ok=true`, `get_fabric_health.ok=true`; `v54-ingress` and `fabric-runtime` both HTTP 200.

### Closure status

- **Built**: exact synthetic V11 immutable image and test-only service.
- **Run**: real Cloud Run revision Ready; real HTTP isolated proxy; real provider logging.
- **Observed**: private IAM denial, application synthetic authorization fail-closed, no production revision change.
- **Proved (scoped)**: real deployment and specified readback properties, not Google refresh.
- **Open**: `/healthz` 404, live OAuth/ChatGPT native refresh, comprehensive rollback execution, durable free-tier cost beyond the dated Free Trial contract.
- **Next admissible move**: diagnose reserved/misrouted `/healthz` route without modifying production; do not deploy another test service or replay old scripts.

## Root-cause lead for the `/healthz` residual

A 2026-09-03 resolution in Google Developer forums identifies **Cloud Run Google Frontend interception of some URL paths ending in `z`**, specifically `/healthz`, producing Google's HTML 404 before reaching the container. It reports that changing the path to `/health` resolved the symptom:
https://discuss.google.dev/t/cloud-run-services-return-google-branded-404-on-public-run-app-url-despite-ready-true-correct-iam-ingress-all-reproduced-across-2-projects-2-accounts-zero-request-logs/381607/6

This is a **third-party diagnosis and a plausible carrier**, not a certified Google-wide policy or a fix replayed on this V11 image. Our internal A/B observations (`/healthz` => GFE HTML 404; `/healthz/` => FastAPI 307; `/authorize` => FastAPI 503 under authenticated proxy) are consistent with that mechanism. **Do not rebuild/redeploy the immutable V11 image merely to claim closure.** If a successor test-only source is approved, add a `/health` alias, publish under a new digest with independent tests, and demonstrate 200 from the protected endpoint before closing the route gate.
