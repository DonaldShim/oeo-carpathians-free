# C-SCI V2 / ARC3 prospective holdout carrier admission — 2026-10-29

## Goal
Prospective comparison on previously unseen **game mechanics**, not simply a Cloud Run completion or reused historical ARC3 trajectory. Fair frozen A0↔candidate comparison must count SDK actions, Qwen calls/tokens, CPU/GPU/wall time, and require real GOAL with matched reset/initial state and no source witness leakage.

## Source integrity
- Registry reports 17 ARC3 carriers, but registered entries alone do not imply unobserved-game readiness.
- `ARC3-ACTION-BASIS-CAUSAL-PROBE-V1`: fully fetched and exact SHA-256 verified `469b992c1a9a1927d3fb73edffafa7e5495eb2fc97a84c67d5235e1846297965`, 66439 bytes. Its top-level run.sh executes `runtime/action_basis_probe.py --backend historical`.
- README and source `HistoricalBackend` explicitly require `r34_base.py`, archived R31/R36/R42 certificates, and historical replay corpus. Neither candidate `ARC3_R36_CEGAR_OPERATOR_BIRTH_20260928/r34_base.py` nor `ARC3_R35_COUNTERFACTUAL_PREDICATE_20260927/r34_base.py` is embedded in the exact registered bundle. Therefore complete source-to-sandbox reproduction and genuinely new-game admission **FAIL**. The source's synthetic backend is `TEST_ONLY`, explicitly not eligible for science.
- `ARC3-R55-GCC-PROVENANCE-RECOVERY-V1`: downloaded and exact SHA-256 verified `5d20b519f651e116a7ae457b8167bb8afd1da3856be738ed60003af4d5da1e45`, 17266 bytes. Its own README explicitly declares `OPEN / PROOF_DEBT` unless a valid identity-bound R54 response is supplied; a positive LP projection alone requires external replay.
- Existing C-SCI V2 `c-sci-v2-arc3-kolo10-20261029` remains present; legacy minute scheduler `c-lab-queue-poll-public` remains `PAUSED`. No scientific work, production change, deletions, SDK action spend, or Qwen spend occurred in this admission step.

## Verdict
**AFFIRMED** exact source retrieval, provenance, and blocker detection.
**REJECTED** treating historical runtime or synthetic backend as unseen-game holdout.
**OPEN** prospective independent ARC3 gain and real GOAL; no newly counted wins.

## Next admissible runnable experiment
1. Secure a source-complete, checksum-stable candidate + baseline A0 with full native SDK environment and access to 6 entirely different withheld game families not represented in candidate training/selection.
2. Pre-register seeds, reset/saved-action equivalence, per-family matched time/action/Qwen-token budgets, and hidden-witness isolation. Reject stale cached trajectories as new-game evidence.
3. Canary one paired game using native backend, obtain identical starts and measurable state responses from ≥2 distinct interventions, and archive full action-response traces.
4. Only then stage bounded Cloud Run runner in C-SCI V2, use immutable ZIP/GCS CAS and independent scientific receipt; show per-family wins, cost, CPU/GPU, and judge no regression vs A0.
5. If all 6 families lack authorized native runnable environment, stop with explicit `HOLDOUT_RUNTIME_UNAVAILABLE`, not fake success.
