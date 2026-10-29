# C-SCI V2 — ARC3 KOLO10 real scientific execution and same-ID replay (2026-10-29)

**Status: AFFIRMED_SCOPED_SCIENTIFIC_DONE.** Not an ARC3 competition win, not independent unseen-game transfer, and not a global theorem.

## Exact immutable source

- Canonical registered case: `ARC3`.
- Carrier: `ARC3-KOLO10-SELF-ATTRIBUTING-MECHANISM-FOUNDRY-V1`.
- Original complete bundle SHA-256: `fe5aa32cd250e9268fe367c2136605f95eaa51b7aa58277b843bd58632a0bde3`, 155803 bytes, 107 ZIP entries, 106 entries enumerated by its internal SHA manifest.
- The original carrier code was **not** changed. In canonical `run.sh` the entrypoint is `runtime/run_v10.py`; the carrier originally emits only `SCIENTIFIC_RESULT.json`.
- Source transferred with integrity gate to `gs://c-sci-clean-v1-855271818322/sources/ARC3/ARC3-KOLO10-SELF-ATTRIBUTING-MECHANISM-FOUNDRY-V1/fe5aa32cd250e9268fe367c2136605f95eaa51b7aa58277b843bd58632a0bde3.zip`, generation `1793286600058277`.
- Dedicated isolated Cloud Run Job `c-sci-v2-arc3-kolo10-20261029`, service account `c-sci-v1-worker@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com`, 2 CPU, 1 GiB RAM, maxRetries=0, timeout=360 seconds.
- Deployed C-SCI wrapper source `c_sci_v2/runner/registered_arc3_kolo10_executor_r3_pydantic.py`, SHA-256 `1c3ac53172e3f371faae366fbaa915ea447d5504c856c7ba104db041dfadafb3`. Actual Cloud Run Job configuration decoded and hashed at admission. The independent wrapper checks the entire source ZIP SHA and manifest before running the unmodified scientific code.
- Successful execution image resolved to `mirror.gcr.io/library/python@sha256:6d10e720318bd84cc3d88af92bb5a47189222e17620a2fd214da6445e4afb679`.
- Pinned top-level scientific packages installed at runtime: `numpy==1.26.4`, `mpmath==1.3.0`, `pydantic==2.10.6`. Runtime pip/network dependency remains an operational fragility.

## Failure history retained, not hidden

1. `c-sci-v2-arc3-kolo10-20261029-62wqv`: failed `rc=1` inside original scientific entrypoint. Separate immutable `runs/c-sci-arc3-kolo10-20261029-r1/failure.json`; **no false receipt**.
2. `c-sci-v2-arc3-kolo10-20261029-l969p`: exact cause `ModuleNotFoundError: No module named 'pydantic'`. Immutable `runs/c-sci-arc3-kolo10-20261029-r2/failure.json`. The original source archive was unchanged; the isolated runtime received Pydantic 2.
3. `c-sci-v2-arc3-kolo10-20261029-vjgqp`: first real **SUCCESS**; `Completed=True` at `2026-10-29T15:20:38.932660Z`; process `exit(0)`; scoped science declared PASS by its actual `hard_gate`.

## Independent evidence and result

- Result: `gs://c-sci-clean-v1-855271818322/runs/c-sci-arc3-kolo10-20261029-r3/SCIENTIFIC_RESULT.json`, **SHA-256 `71c29a990b0dc9f82dd3c82c121049bcac7b4e9ff4ea04742542f960d8574e3f`**, 17895 bytes, GCS generation `1793287234547549`.
- Terminal: `gs://c-sci-clean-v1-855271818322/runs/c-sci-arc3-kolo10-20261029-r3/receipt.json`, **SHA-256 `30ec265d93499b6019245f684009fa0cd4a2433c7c2008078dd4b7d6174099f9`**, 740 bytes, GCS generation `1793287234654175`.
- Receipt schema `C_SCI_TERMINAL_RECEIPT_V2`, source SHA, primary SHA+size, `scientific_process_rc=0`, `scoped_scientific_done=true`, `new_unseen_arc3_goal=false`, `publisher=C_SCI_V2_OWN_WRAPPER_NOT_V54`.
- Scientific status: `AFFIRMED_SCOPED_SELF_ATTRIBUTING_MECHANISM_FOUNDRY__TRANSFER_FRUIT_OPEN`.
- Independent Node.js validator `independent_arc3_validator.js` returned `INDEPENDENT_ARC3_ADMISSION=PASS`; all original `hard_gate` fields true, 8/8 factorial arms match original source archive, fresh LS20 replay has local `level_gain=1` relative to control, but unseen target improvement OPEN.
- Independently recomputed Python-compatible semantic hash from the original numeric lexemes in JSON: `a3f68477475802ac59c495e6bee1e896c382af02ad9b3777ea2e7442867150d5` equals the carrier's semantic SHA. Naive JavaScript JSON serialization differed due to loss of `1.0` numeric format; this was isolated as a coordinate artifact and corrected, not ignored.
- Original outcome includes RH OPEN and explicitly rejects claims of global RH proof or general unseen ARC3 GOAL.

## Prospective same-ID replay

- Second real execution: `c-sci-v2-arc3-kolo10-20261029-tkw2c`, `Completed=True`, `2026-10-29T15:25:59.219018Z`, `exit(0)`.
- Cloud Run logs `2026-10-29T15:25:56Z`: `C_SCI_V2_ARC3_SCOPED_DONE=true`; both `RESULT_GCS_GENERATION=REPLAY_IDENTICAL` and `RECEIPT_GCS_GENERATION=REPLAY_IDENTICAL`. Both actual GCS generations remained unchanged.
- This proves idempotent admission for this frozen carrier/input/result ID, not all arbitrary future carriers.

## Legacy and OAuth non-regression

- The historical `c-lab-queue-poll-public` remains **PAUSED** and `c-lab-queue-dispatcher` has zero Cloud Functions Invoker bindings. Old V54 publisher/validator, old Batch VM agent and old automatic dispatcher were not used.
- Read-only `C_Lab_OAuth_Gateway_V3.get_control_health` `ok=true` at `2026-10-29T15:27:30Z`. `get_fabric_health` `ok=true`, `v54-ingress` and `fabric-runtime` HTTP 200 at `15:27:34Z`. Canonical C-Lab was not changed; no prior archives deleted.

## Gate report

`source_provenance=AFFIRMED`
`independent_cloud_execution=AFFIRMED`
`scientific_done_scoped=AFFIRMED`
`primary_plus_receipt_sha=AFFIRMED`
`same_id_cloud_replay=AFFIRMED`
`old_V54_dependency=REJECTED_FOR_THIS_ROUTE`
`new_unseen_goal=OPEN`
`generic_carrier_runtime=OPEN`
`fully_offline_pinned_deps=OPEN`
`production_science_cutover=OPEN`.

The main scientific claim is **local scoped causal quotient credit**. Do not use this certificate to advertise a competition victory or proof of universal AGI.
