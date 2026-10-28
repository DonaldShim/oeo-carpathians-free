# C-Lab OAuth Gateway V3 — live evidence

Gateway: https://c-lab-oauth-gateway-v3-855271818322.europe-west1.run.app/mcp

Runtime revision: `c-lab-oauth-gateway-v3-httpfix0574`.
Image: `sha256:f88b6f09628d14efee1c6c7a0697c7db1785c47e41d73ba4990709a75d47204c`.
Source commit: `59a72290b6f61f1ae48cd4752f1e4f220a9b23c6`.
Source manifest: `0574b758040505496ebaa75b783ad49e455f84202eb602d1e4e80ea39d98721c`.

## Verified on 2026-10-28

- 60 local tests and independently built Linux CI image.
- Actual Firestore concurrency, replay revocation, refresh fencing, independent readback.
- Actual encrypted Drive file upload, independent download SHA, revoked-only restore into isolated Firestore namespace; restored old bearers cannot authorize.
- Google personal offline consent completed. Real Google authorization-code exchange issued required access/ID/refresh credentials. No token contents exported.
- Ordinary ChatGPT Web connected to this Gateway; two real canonical health reads.
- Native ChatGPT refresh at 14:29:18 UTC, after previous Gateway access expiry at 14:29:13 UTC; read returned `ok=true` at 14:29:21 UTC, no reconnect.
- Canonical C-Lab production generation 80 and 100% custody-v1 production revision unchanged.

## Separate gate still requiring elapsed real time

Initial Google access expiry is 2026-10-28T15:26:24Z (17:26:24 Europe/Kyiv).
Google post-expiry refresh is OPEN until a real read after that time yields a Google refresh success and a real upstream response. Native Gateway refresh does not prove this separate gate. Do not change expiry fields or clocks.

## Explicit operational limits

- Gateway exposes only `get_control_health`, `get_controller_status`, `get_fabric_health`.
- The existing delegated Drive connector/operator backup workflow is verified. Cloud Run does not have independent delegated personal Drive credentials; automated runtime Drive backup is not asserted.
- Backup restoration never resurrects active OAuth credentials. Restored grant metadata is revoked and requires new consent.
- Expired OAuth authorization is rejected immediately. Physical cleanup is opportunistic and bounded, not an idle-time deletion SLA.
- Cloud Run min=0/max=1. Firestore free tier was verified. No new mandatory paid fixed capacity; exact incremental cost is not zero-certified.
- No scientific jobs, VM changes, Host CAS install, serving cutover, or canonical traffic changes.

## Recovery boundary

Preserve Firestore as authoritative; never roll back access/refresh documents from Drive. Use Secret Manager version references without exporting secret payloads.
For a bad Gateway revision, the original fail-closed revision `c-lab-oauth-gateway-v3-source12ca` remains available in the separate Gateway service. It denies OAuth because configuration is incomplete. Switching to it sacrifices availability and is not a successful OAuth restoration.
The current healthy image digest above can be redeployed through the same controlled service after configuration/secret references are independently verified. No such recovery deployment is performed by these instructions.
Drive failure must leave live Firestore unchanged. Google refresh UNKNOWN requires new consent; do not blindly replay an uncertain refresh request.

## Evidence interpretation

Local test certificates, provider readbacks, real native browser observations, and Google expiry proof are separate. Historical failed CI, expired unconsumed OAuth state and transport errors are retained. No local or synthetic result certifies live Google refresh.
