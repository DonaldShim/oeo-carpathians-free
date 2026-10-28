# C-Lab OAuth Gateway V3 — cumulative candidate

Original V2 archive SHA256: e6104d277691a01c1b59e744280b8b57137229ba532ea4e4269b49863ac4e957.
All 32 entries in the original V2 manifest verified before modification.
The legacy SQL implementation, tests and deployment documents are retained as
history. V3 serves `gateway.bootstrap:app`, exclusively Firestore at runtime.

## Proven locally / against real Firestore

V3 adds closed handling of unknown Google refresh responses and abandoned leases,
lease epoch/deadline fencing, atomic access/grant snapshots, duplicate parameter
rejection, explicit public-client authentication rules, RPC response identity,
bounded killable outbound HTTP children and independently downloaded Drive SHA.
Restoration yields only revoked grant metadata; no old bearer/code/refresh or
Google credential is restored. Drive is never an authority for token rotation.

Real Firestore concurrency was exercised in an isolated prefix using the existing
authenticated operator. Four code redeemers produced one winner; four refresh
rotators produced one winner and replay revoked the family. Competing Google
refresh was fenced. The external Google provider in this replay was synthetic.
All 15 newly created test documents were deleted. This is not runtime-SA or
Google/ChatGPT OAuth proof.

## Deployment and authentication gates

The image can start safely without OAuth secrets: `/health` returns 503 with
`ready=false`; all other routes deny access. Missing credentials are never
replaced by synthetic credentials. A first deployment in that state is a
configuration-incomplete candidate, not a functional OAuth deployment.

The canonical MCP currently admits only Google client
855271818322-o0hvrvsmj7nb14238mrkn069aeta5ln3.apps.googleusercontent.com.
The official Google Auth Platform readback on 2026-10-28 showed its sole redirect
as https://chatgpt.com/connector_platform_oauth_redirect. The new Gateway callback
is not registered. Editing this production client or its audience allowlist is
outside this task's unconditional authorization. A new Google client alone does
not make canonical MCP access work.

Personal Drive backup needs delegated `drive.file` consent; a bare service
account cannot own files in personal My Drive. No personal credentials are
included in this source. Real Google expiry/refresh and native ChatGPT
expiry/refresh remain separate required live acceptance gates.

## Limits and recovery

Cloud Run: separate service, min=0, max=1, concurrency=2; no production cutover.
The existing Firestore default database remains authoritative. The initial
source has per-IP authorization limits and finite token/grant validity; automatic
TTL deletion and whole-service abuse/cost limits are additional operational gates,
not asserted as complete merely from expiry checks.

Do not replay an UNKNOWN Google refresh outcome. Reconsent is required.
Do not route production traffic or claim FULL_CERTIFIED from these local results.
