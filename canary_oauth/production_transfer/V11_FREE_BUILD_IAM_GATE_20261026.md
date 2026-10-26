# C-Lab V11: bounded FREE-ONLY Cloud Build unblock (26 Oct 2026)

**Status: BECOMING; no Cloud Run deployment and no IAM or build changes performed in this step.**

## Independent source evidence
- User handoff: `C_LAB_OAUTH_V11_CLOUD_RUN_HANDOFF(1).zip`.
- Embedded source `original/V11.zip`, SHA256: `d2c7352ddcd0aad52a92f8fda24f88f672e6669286e5532a649e1554e0968be1`, 14853 bytes, CRC PASS.
- Terminal certificate SHA256: `b44dd997b81890720920346e0a480fce64214f058743de5cce22aad6f743e8d9`; 38/38 referenced evidence SHA digests checked and matched.
- Failure: `gcloud builds submit` returned `FAILED_PRECONDITION: invalid bucket project-4e9f56f4-a524-4759-91f_cloudbuild; service account 855271818322-compute@developer.gserviceaccount.com does not have access`. No build ID; no Cloud Run revision; 0 science jobs; production unchanged.
- Exact project IAM snapshot says Compute default build SA has `roles/storage.objectViewer` and `roles/run.builder`.
- `roles/storage.objectViewer` has object get/list, but not `storage.buckets.get`. `roles/storage.bucketViewer` has `storage.buckets.get` and `storage.buckets.list` and can be scoped to one bucket. Thus missing bucket metadata access is plausible, **not yet proven**; denial may also arise from IAM deny, conditional policy or different credential scope. Verify effective permission.

## The separate pricing defect
Original `cloudbuild.json` used `options.machineType=E2_MEDIUM`, which is NOT the machine type eligible for the monthly Google Cloud Build free tier. Only `E2_STANDARD_2` in the default pool can use the promotional 2500 free build-minutes per billing account per month. New config here: [cloudbuild-v11-free.json](./artifacts/cloudbuild-v11-free.json) also changes `GCS_ONLY` to `CLOUD_LOGGING_ONLY` and removes `logsBucket`. It still needs source-bucket metadata/read permission for `gcloud builds submit`.

## Exact read-only IAM test — use authorized Cloud Shell / Codex

```bash
set -euo pipefail
P=project-4e9f56f4-a524-4759-91f
B="${P}_cloudbuild"
SA=855271818322-compute@developer.gserviceaccount.com
R="//storage.googleapis.com/projects/_/buckets/${B}"
mkdir -p v11-free-readback

gcloud config get-value project
gcloud storage buckets describe "gs://${B}" --format=json > v11-free-readback/bucket.json
gcloud storage buckets get-iam-policy "gs://${B}" --format=json > v11-free-readback/bucket_iam.json

gcloud policy-intelligence troubleshoot-policy iam "${R}" \
  --principal-email="${SA}" --permission=storage.buckets.get \
  --format=json > v11-free-readback/storage_buckets_get.json

gcloud policy-intelligence troubleshoot-policy iam "${R}" \
  --principal-email="${SA}" --permission=storage.objects.get \
  --format=json > v11-free-readback/storage_objects_get.json

gcloud builds list --project="${P}" --region=europe-west1 \
  --filter='tags:clab-oauth-v11-20261026-01' --format=json \
  > v11-free-readback/builds_reconcile.json

gcloud run services describe c-lab-gcp-control \
  --project="${P}" --region=europe-west1 --format=json \
  > v11-free-readback/production.json

echo 'READ_ONLY_DONE; NO_IAM_MUTATIONS; NO_BUILDS'
```

If Policy Troubleshooter reports **DENIED specifically on `storage.buckets.get`**, inspect deny rules. Under **freshly approved** single-bucket IAM grant and exact policy before/after snapshot only, the minimal predefined role is:

```bash
gcloud storage buckets add-iam-policy-binding \
 gs://project-4e9f56f4-a524-4759-91f_cloudbuild \
 --member=serviceAccount:855271818322-compute@developer.gserviceaccount.com \
 --role=roles/storage.bucketViewer
```

Do **NOT** execute this grant automatically. Ensure no identical binding pre-exists. Independent effective readback must confirm it works. If pre-existing or unrelated concurrent policy changes, stop rather than deleting an unrelated binding. Rollback after bounded build:

```bash
gcloud storage buckets remove-iam-policy-binding \
 gs://project-4e9f56f4-a524-4759-91f_cloudbuild \
 --member=serviceAccount:855271818322-compute@developer.gserviceaccount.com \
 --role=roles/storage.bucketViewer
```

Avoid project `roles/storage.admin`, `roles/editor` and any C-Fabric/science bucket changes.

## ABSOLUTE ZERO ADDITIONAL CHARGES gate

The user now requires **free-only**. Previous $2 allowance is superseded.

Even `E2_STANDARD_2` costs money if the shared billing-account monthly free allocation is exhausted; Cloud Logging, source-bucket storage, egress, image storage, secret versions and Cloud Run requests may have separate costs. Verify actual account quota/cost evidence for each **before submission**. Budgets are alerts, not hard caps; no reliable proof of $0 => STOP and return OPEN.

Only once real IAM readback confirms the required access, free-tier usage/remaining budget is certified, and new authorization to execute exists, build **exactly once**, reconcile; never blind retry.

The only permitted runtime target is a separate **private** `c-lab-oauth-v11-test` Cloud Run service using distinct service identity, not the publicly invokable `c-lab-gcp-control`.

Production traffic preserved 100% and science jobs 0; synthetic V11 never certifies Google OIDC/native ChatGPT refresh.

### Sources
- https://docs.cloud.google.com/storage/docs/access-control/iam-roles
- https://docs.cloud.google.com/policy-intelligence/docs/troubleshoot-access
- https://cloud.google.com/build/pricing
- https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts
