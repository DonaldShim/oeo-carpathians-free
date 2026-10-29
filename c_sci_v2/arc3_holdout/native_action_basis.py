#!/usr/bin/env python3
"""Native offline ARC3 ACTION-BASIS causal admission, NOT an A0/Qwen benchmark.

An exact SDK experiment using 2 disjoint action contrasts and 2 fresh root
replays per planned point. Hidden solution/outcome information is forbidden to
the action-selection policy. A matched random-action control is only a
calibration arm and MUST NOT be called frozen A0.
"""
import argparse
import hashlib
import json
import os
import pathlib
import random
import sys
import time
import traceback
from collections import defaultdict

from arc_agi import Arcade, OperationMode
from arcengine import GameAction


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canon(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def obs_view(obs):
    grid = [[int(z) for z in row] for row in obs.frame[-1]]
    return {
        "frame_sha256": sha(json.dumps(grid, separators=(",", ":")).encode()),
        "levels": int(obs.levels_completed),
        "state": obs.state.name,
        "legal": sorted(set(int(getattr(a, "value", a)) for a in obs.available_actions)),
    }


def choice(action_id):
    if action_id == 6:
        return {"action": 6, "data": {"x": 32, "y": 32}}
    return {"action": int(action_id), "data": None}


def pick_contrasts(legal):
    legal = sorted(set(legal))
    if len(legal) < 4:
        return None
    a, b, c, d = legal[0], legal[-1], legal[1], legal[-2]
    if len({a, b, c, d}) != 4:
        raise ValueError("DUPLICATE_ACTION_BASIS")
    return [[a, b], [c, d]]


def plan(basis):
    # 20 replays in stage A + 8 in stage B, exactly as the parent spec.
    points = []
    for idx, pair in enumerate(basis):
        for amplitude in [-2, -1, 0, 1, 2]:
            action = pair[0] if amplitude > 0 else pair[1]
            seq = [choice(action)] * abs(amplitude)
            for repeat in range(2):
                points.append({"stage": "A", "direction": idx, "amp": amplitude,
                               "repeat": repeat, "sequence": seq})
    for i in [-1, 1]:
        for j in [-1, 1]:
            seq = [choice(basis[0][0] if i > 0 else basis[0][1]),
                   choice(basis[1][0] if j > 0 else basis[1][1])]
            for repeat in range(2):
                points.append({"stage": "B", "direction": [i, j], "amp": None,
                               "repeat": repeat, "sequence": seq})
    assert len(points) == 28 and sum(len(x["sequence"]) for x in points) == 40
    return points


def controls(pts, legal, game, seed):
    # Same number of independent trials and SDK actions as causal basis.
    # This random control is NOT an A0 or model-dependent policy.
    out = []
    for i, point in enumerate(pts):
        rng = random.Random(int(sha(f"{game}|{seed}|{i}|control-v1".encode())[:14], 16))
        seq = [choice(rng.choice(legal)) for _ in point["sequence"]]
        out.append({"stage": point["stage"], "direction": point["direction"],
                    "amp": point["amp"], "repeat": point["repeat"], "sequence": seq})
    return out


def replay(arcade, game, seed, point, root_hash):
    env = arcade.make(game, seed=seed)
    before = obs_view(env.observation_space)
    if before["frame_sha256"] != root_hash:
        raise RuntimeError("ROOT_REPLAY_NOT_DETERMINISTIC")
    start = time.perf_counter()
    charged = 0
    state = env.observation_space
    action_receipts = []
    for action in point["sequence"]:
        if state.state.name != "NOT_FINISHED":
            break
        idx = action["action"]
        if idx not in obs_view(state)["legal"]:
            break
        state = env.step(GameAction.from_id(idx), data=action["data"]) if idx == 6 else env.step(GameAction.from_id(idx))
        charged += 1
        v = obs_view(state)
        action_receipts.append({"action": idx, "frame": v["frame_sha256"],
                                "levels": v["levels"], "state": v["state"]})
    final = obs_view(state)
    return {"stage": point["stage"], "direction": point["direction"], "amp": point["amp"],
            "repeat": point["repeat"], "planned_actions": len(point["sequence"]),
            "charged_actions": charged, "levels": final["levels"],
            "level_gain": final["levels"] - before["levels"],
            "won": final["state"] == "WIN",
            "state": final["state"], "final_sha256": final["frame_sha256"],
            "trace_sha256": sha(canon(action_receipts)),
            "wall_s": round(time.perf_counter() - start, 5)}


def pair_test(arcade, game, seed):
    game_start = time.perf_counter()
    root = obs_view(arcade.make(game, seed=seed).observation_space)
    basis = pick_contrasts(root["legal"])
    if basis is None:
        return {"game": game, "seed": seed, "status": "OPEN_INSUFFICIENT_ACTION_BASIS",
                "root": root, "paid_sdk_actions": 0, "qwen_tokens": 0}
    pts = plan(basis)
    cal = controls(pts, root["legal"], game, seed)
    streams = {}
    for arm, stream in (("ACTION_BASIS_NATIVE", pts), ("MATCHED_RANDOM_NOT_A0", cal)):
        rows = []
        for p in stream:
            rows.append(replay(arcade, game, seed, p, root["frame_sha256"]))
        streams[arm] = {
            "runs": rows, "paid_sdk_actions": sum(r["charged_actions"] for r in rows),
            "best_level_gain": max(r["level_gain"] for r in rows),
            "best_win": any(r["won"] for r in rows),
            "raw_positive_count": sum(r["level_gain"] > 0 for r in rows),
            "unique_final_frames": len(set(r["final_sha256"] for r in rows)),
        }
    # Credit only when identical causal interventions (repeat 0/1)
    # produce the same positive level gain or GOAL, not just visual changes.
    groups = defaultdict(list)
    for p, row in zip(pts, streams["ACTION_BASIS_NATIVE"]["runs"]):
        k = json.dumps({"stage": p["stage"], "direction": p["direction"],
                        "amp": p["amp"], "sequence": p["sequence"]}, sort_keys=True)
        groups[k].append(row)
    witnesses = []
    for key, pair in groups.items():
        if len(pair) == 2 and pair[0]["trace_sha256"] == pair[1]["trace_sha256"]:
            if pair[0]["level_gain"] > 0 or pair[0]["won"]:
                witnesses.append({"coordinate": json.loads(key), "gain": pair[0]["level_gain"],
                                  "won": pair[0]["won"],
                                  "trace_sha256": pair[0]["trace_sha256"]})
    gain = streams["ACTION_BASIS_NATIVE"]["best_level_gain"] - streams["MATCHED_RANDOM_NOT_A0"]["best_level_gain"]
    a_actions = streams["ACTION_BASIS_NATIVE"]["paid_sdk_actions"]
    c_actions = streams["MATCHED_RANDOM_NOT_A0"]["paid_sdk_actions"]
    return {
        "game": game, "seed": seed, "status": "AFFIRMED_SCOPED_CAUSAL_GAIN" if witnesses and gain > 0
                   else "OPEN_NO_CERTIFIED_CAUSAL_ADVANTAGE",
        "basis": basis, "root": root, "double_replay_witnesses": witnesses,
        "level_gain_advantage_over_random_control": gain, "arms": streams,
        "sdk_action_parity": a_actions == c_actions,
        "sdk_action_delta": a_actions - c_actions,
        "model_calls": 0, "qwen_tokens": 0, "gpu_seconds": 0,
        "wall_s": round(time.perf_counter() - game_start, 3),
        "comparison_to_frozen_gpu_A0": "NOT_PERFORMED",
        "unseen_competition_game": False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--precommit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-pairs", type=int, default=12)
    args = ap.parse_args()
    raw = pathlib.Path(args.precommit).read_bytes()
    spec = json.loads(raw)
    if spec["schema"] != "C_SCI_ARC3_ACTION_BASIS_NATIVE_PRECOMMIT_V1":
        raise RuntimeError("PRECOMMIT_SCHEMA_FAIL")
    if spec["game_source"] != "OFFLINE_PUBLIC_SDK" or spec["a0_gpu_arm_executed"] is not False:
        raise RuntimeError("ADMISSION_FAILED")
    pairs = [(g, s) for g in spec["games"] for s in spec["seeds"]]
    if len(set(pairs)) != len(pairs) or len(pairs) > args.max_pairs or not pairs:
        raise RuntimeError("PAIR_LIMIT_FAIL")
    if args.max_pairs > 12 or any(g.split("-")[0] in spec["positive_train_families"] for g, _ in pairs):
        raise RuntimeError("HOLDOUT_ADMISSION_FAIL")
    arcade = Arcade(operation_mode=OperationMode.OFFLINE,
                    environments_dir=spec["environments_dir"])
    names = {e.game_id for e in arcade.available_environments}
    if any(g not in names for g in spec["games"]):
        raise RuntimeError("NATIVE_GAME_MISSING")
    start = time.perf_counter()
    rows = []
    for game, seed in pairs:
        try:
            row = pair_test(arcade, game, int(seed))
        except Exception as exc:
            row = {"game": game, "seed": seed, "status": "OPEN_NATIVE_ERROR",
                   "reason": type(exc).__name__ + ":" + str(exc)[:200]}
        rows.append(row)
        print(json.dumps({"game": game, "seed": seed, "status": row["status"],
                          "gain": row.get("level_gain_advantage_over_random_control", None),
                          "time_s": row.get("wall_s", None)}, sort_keys=True), flush=True)
    report = {
        "schema": "C_SCI_ARC3_NATIVE_ACTION_BASIS_REPORT_V1",
        "precommit_sha256": sha(raw), "game_source": spec["game_source"],
        "source_lineage": spec["source_lineage"],
        "scope": "SOURCE_DISJOINT_FAMILIES_PREVIOUSLY_SCREENED_ROOTS_NEW_SEEDS",
        "arm_frozen_A0_executed": False, "external_hidden_holdout": False,
        "registered_action_basis_carrier_executed_byte_identical": False,
        "game_count": len(spec["games"]), "pair_count": len(rows),
        "native_successful_pairs": sum("arms" in x for x in rows),
        "action_basis_positive_witness_pairs": sum(bool(x.get("double_replay_witnesses")) for x in rows),
        "certified_scoped_gain_over_random": sum(x.get("status") == "AFFIRMED_SCOPED_CAUSAL_GAIN" for x in rows),
        "real_new_unseen_arc3_GOAL_vs_A0": None,
        "charged_sdk_actions": sum(sum(y["paid_sdk_actions"] for y in x.get("arms", {}).values()) for x in rows),
        "charged_qwen_tokens": 0,
        "native_cpu_wall_s": round(time.perf_counter()-start, 3),
        "scientific_status": "OPEN_VS_REAL_FROZEN_A0",
        "rows": rows
    }
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_bytes(canon(report))
    print("NATIVE_ACTION_BASIS_REPORT_SHA256="+sha(canon(report)),flush=True)
    print("REAL_A0_COMPARISON_PERFORMED=false",flush=True)


if __name__ == "__main__":
    main()
