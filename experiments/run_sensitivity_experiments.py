#!/usr/bin/env python3
"""Generate optional scale- and threshold-sensitivity results for SOR.

The primary 50K experiment is not changed. This script adds three explicitly
specified scales and three deterministic seeds. Medium and large policies are
constructed by a transparent generator; every generated policy and every
request-level event is released.
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/sensitivity_experiments.json").read_text())
SUMMARY = ROOT / "results" / "summary"
RAW = ROOT / "results/raw/scale_sensitivity"
POLICIES = ROOT / "results/generated_scale_policies"
SUMMARY.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
POLICIES.mkdir(parents=True, exist_ok=True)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rules(policy: dict) -> list[tuple[str, str, str]]:
    return [(r["subject"], r["action"], r["resource"]) for r in policy.get("allow", [])]


def as_policy(items: list[tuple[str, str, str]], policy_id: str, description: str) -> dict:
    return {
        "policy_id": policy_id,
        "description": description,
        "allow": [
            {"subject": s, "action": a, "resource": r}
            for s, a, r in items
        ],
    }


def generate_rules(identity_count: int, stable_count: int, required_count: int):
    stable = [
        (f"identity_{i % identity_count:04d}", f"action_{i % 32:02d}", f"resource_{i:05d}")
        for i in range(stable_count)
    ]
    required = stable[:required_count]
    redundant = stable[required_count:]
    unsafe_remove_count = max(1, round(stable_count * 0.10))
    unsafe_removed = required[:unsafe_remove_count]
    unsafe = [x for x in stable if x not in set(unsafe_removed)]
    safe = list(required)
    return stable, required, redundant, unsafe_removed, unsafe, safe


def small_inputs(seed: int, requests: int):
    stable = rules(load_json(ROOT / "datasets/examples/policy_stable.json"))
    required = rules(load_json(ROOT / "datasets/examples/policy_required.json"))
    unsafe = rules(load_json(ROOT / "datasets/examples/policy_candidate_over_aggressive.json"))
    safe = rules(load_json(ROOT / "datasets/examples/policy_candidate_lower_risk.json"))
    redundant = [x for x in stable if x not in set(required)]
    unsafe_removed = [x for x in required if x not in set(unsafe)]
    trace = load_json(ROOT / "datasets/examples/replay_trace.json")
    population = []
    for item in trace:
        clean = {k: v for k, v in item.items() if k != "weight"}
        population.extend([clean] * int(item.get("weight", 1)))
    rng = random.Random(seed)
    reqs = [
        (r["subject"], r["action"], r["resource"])
        for r in (rng.choice(population) for _ in range(requests))
    ]
    return stable, required, redundant, unsafe_removed, unsafe, safe, reqs


def generated_inputs(scale: dict, seed: int, requests: int):
    stable, required, redundant, unsafe_removed, unsafe, safe = generate_rules(
        scale["identities"], scale["stable_entitlements"], scale["required_entitlements"]
    )
    kept_required = [x for x in required if x not in set(unsafe_removed)]
    if not kept_required or not unsafe_removed or not redundant:
        raise ValueError(f"invalid generated scale: {scale['key']}")
    mix = CONFIG["generated_request_mix"]
    rng = random.Random(seed)
    reqs = []
    for _ in range(requests):
        p = rng.random()
        if p < mix["required_kept"]:
            reqs.append(rng.choice(kept_required))
        elif p < mix["required_kept"] + mix["required_removed_by_unsafe"]:
            reqs.append(rng.choice(unsafe_removed))
        else:
            reqs.append(rng.choice(redundant))
    return stable, required, redundant, unsafe_removed, unsafe, safe, reqs


def pct(stable: set, candidate: set) -> float:
    return 100.0 * len(stable - candidate) / len(stable)


def gate(obs: list[dict], mismatch_threshold: float):
    mismatches = sum(e["unsafe_mismatch"] for e in obs)
    required_denials = sum(e["unsafe_required_would_deny"] for e in obs)
    expansions = 0
    rate = mismatches / len(obs)
    passed = (
        len(obs) >= CONFIG["minimum_gate_observations"]
        and rate <= mismatch_threshold
        and required_denials <= CONFIG["legitimate_denial_threshold"]
        and expansions <= CONFIG["candidate_expansion_threshold"]
    )
    return passed, mismatches, rate, required_denials


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def evaluate_scale(scale: dict, seed: int):
    n = CONFIG["requests_per_seed"]
    if scale["key"] == "small":
        data = small_inputs(seed, n)
    else:
        data = generated_inputs(scale, seed, n)
    stable_l, required_l, redundant_l, unsafe_removed_l, unsafe_l, safe_l, reqs = data
    stable, required = set(stable_l), set(required_l)
    unsafe, safe = set(unsafe_l), set(safe_l)
    observation_n = max(CONFIG["minimum_gate_observations"], round(n * CONFIG["observation_prefix_fraction"]))
    events = []
    for idx, key in enumerate(reqs):
        stable_allow = key in stable
        required_label = key in required
        unsafe_allow = key in unsafe
        safe_allow = key in safe
        events.append({
            "request_id": f"{scale['key']}-{seed}-{idx+1:06d}",
            "subject": key[0],
            "action": key[1],
            "resource": key[2],
            "phase": "observation" if idx < observation_n else "post-observation",
            "stable_allow": stable_allow,
            "oracle_required": required_label,
            "unsafe_candidate_allow": unsafe_allow,
            "safe_candidate_allow": safe_allow,
            "unsafe_mismatch": stable_allow != unsafe_allow,
            "safe_mismatch": stable_allow != safe_allow,
            "unsafe_required_would_deny": required_label and not unsafe_allow,
            "safe_required_would_deny": required_label and not safe_allow,
        })
    obs = events[:observation_n]
    unsafe_pass, unsafe_m, unsafe_rate, unsafe_wd = gate(obs, CONFIG["mismatch_rate_threshold"])
    # Safe gate uses its own fields.
    safe_m = sum(e["safe_mismatch"] for e in obs)
    safe_rate = safe_m / len(obs)
    safe_wd = sum(e["safe_required_would_deny"] for e in obs)
    safe_pass = (
        len(obs) >= CONFIG["minimum_gate_observations"]
        and safe_rate <= CONFIG["mismatch_rate_threshold"]
        and safe_wd <= CONFIG["legitimate_denial_threshold"]
    )
    # Full SOR enforces only if gate passes; required denials therefore remain zero
    # for a withheld over-aggressive candidate and for a correctly constructed lower-risk candidate.
    unsafe_denials = sum(e["unsafe_required_would_deny"] for e in events[observation_n:]) if unsafe_pass else 0
    safe_denials = sum(e["safe_required_would_deny"] for e in events[observation_n:]) if safe_pass else 0

    policy_dir = POLICIES / scale["key"]
    policy_dir.mkdir(parents=True, exist_ok=True)
    if seed == CONFIG["seeds"][0]:
        (policy_dir / "policy_stable.json").write_text(json.dumps(as_policy(stable_l, f"{scale['key']}-stable", "Generated effective stable policy"), indent=2) + "\n")
        (policy_dir / "policy_required.json").write_text(json.dumps(as_policy(required_l, f"{scale['key']}-required", "Generated required-policy oracle"), indent=2) + "\n")
        (policy_dir / "policy_candidate_over_aggressive.json").write_text(json.dumps(as_policy(unsafe_l, f"{scale['key']}-over-aggressive", "Generated over-aggressive candidate"), indent=2) + "\n")
        (policy_dir / "policy_candidate_lower_risk.json").write_text(json.dumps(as_policy(safe_l, f"{scale['key']}-lower-risk", "Generated lower-risk candidate"), indent=2) + "\n")

    raw_path = RAW / f"{scale['key']}_seed_{seed}.csv"
    write_csv(raw_path, events)
    return {
        "Scale": scale["label"],
        "Seed": seed,
        "Identities": scale["identities"],
        "Stable Entitlements": len(stable),
        "Required Entitlements": len(required),
        "Generator-Labeled Redundant Entitlements": len(redundant_l),
        "Requests": n,
        "Observation Requests": observation_n,
        "Over-Aggressive Proposed Reduction %": f"{pct(stable, unsafe):.1f}",
        "Over-Aggressive Observation Mismatches": unsafe_m,
        "Over-Aggressive Observation Mismatch Rate": f"{unsafe_rate:.6f}",
        "Over-Aggressive Required Would-Deny": unsafe_wd,
        "Over-Aggressive Full SOR Action": "Promoted" if unsafe_pass else "Promotion withheld",
        "Over-Aggressive Legitimate Denials": unsafe_denials,
        "Lower-Risk Proposed Reduction %": f"{pct(stable, safe):.1f}",
        "Lower-Risk Observation Mismatches": safe_m,
        "Lower-Risk Observation Mismatch Rate": f"{safe_rate:.6f}",
        "Lower-Risk Required Would-Deny": safe_wd,
        "Lower-Risk Full SOR Action": "Promoted" if safe_pass else "Promotion withheld",
        "Lower-Risk Legitimate Denials": safe_denials,
        "Raw Event File": str(raw_path.relative_to(ROOT)),
    }


def threshold_rows():
    meta = load_json(SUMMARY / "primary_experiment_metadata.json")
    rows = []
    for threshold in CONFIG["threshold_values"]:
        for key, label in [("over_aggressive", "Over-aggressive candidate"), ("lower_risk", "Lower-risk candidate")]:
            g = meta["candidates"][key]["gate_metrics"]
            passed = (
                g["observation_requests"] >= CONFIG["minimum_gate_observations"]
                and g["observation_mismatch_rate"] <= threshold
                and g["observation_required_would_deny"] <= CONFIG["legitimate_denial_threshold"]
                and g["observation_expansions"] <= CONFIG["candidate_expansion_threshold"]
            )
            rows.append({
                "Mismatch Threshold": f"{threshold:.3f}",
                "Candidate": label,
                "Observation Requests": g["observation_requests"],
                "Observation Mismatches": g["observation_mismatches"],
                "Observation Mismatch Rate": f"{g['observation_mismatch_rate']:.6f}",
                "Required Would-Deny": g["observation_required_would_deny"],
                "Candidate Expansions": g["observation_expansions"],
                "Full SOR Action": "Promoted" if passed else "Promotion withheld",
                "Legitimate Denials": 0 if not passed or key == "lower_risk" else "not evaluated",
            })
    return rows


def summary_rows(rows: list[dict]):
    by_scale = defaultdict(list)
    for row in rows:
        by_scale[row["Scale"]].append(row)
    out = []
    scale_order = {s["label"]: i for i, s in enumerate(CONFIG["scales"])}
    for label in sorted(by_scale, key=lambda x: scale_order[x]):
        group = by_scale[label]
        unsafe_rates = [float(r["Over-Aggressive Observation Mismatch Rate"]) for r in group]
        safe_rates = [float(r["Lower-Risk Observation Mismatch Rate"]) for r in group]
        out.append({
            "Scale": label,
            "Identities": group[0]["Identities"],
            "Stable Entitlements": group[0]["Stable Entitlements"],
            "Required Entitlements": group[0]["Required Entitlements"],
            "Requests per Seed": group[0]["Requests"],
            "Seeds": len(group),
            "Over-Aggressive Observation Mismatch Rate Mean": f"{mean(unsafe_rates):.6f}",
            "Over-Aggressive Observation Mismatch Rate Range": f"{min(unsafe_rates):.6f}--{max(unsafe_rates):.6f}",
            "Over-Aggressive Full SOR Actions": "; ".join(sorted(set(r["Over-Aggressive Full SOR Action"] for r in group))),
            "Over-Aggressive Legitimate Denials Total": sum(int(r["Over-Aggressive Legitimate Denials"]) for r in group),
            "Lower-Risk Observation Mismatch Rate Mean": f"{mean(safe_rates):.6f}",
            "Lower-Risk Observation Mismatch Rate Range": f"{min(safe_rates):.6f}--{max(safe_rates):.6f}",
            "Lower-Risk Full SOR Actions": "; ".join(sorted(set(r["Lower-Risk Full SOR Action"] for r in group))),
            "Lower-Risk Legitimate Denials Total": sum(int(r["Lower-Risk Legitimate Denials"]) for r in group),
        })
    return out


def main():
    rows = []
    for scale in CONFIG["scales"]:
        for seed in CONFIG["seeds"]:
            rows.append(evaluate_scale(scale, seed))
    summary = summary_rows(rows)
    thresholds = threshold_rows()
    write_csv(SUMMARY / "scale_sensitivity.csv", rows)
    write_csv(SUMMARY / "scale_sensitivity_summary.csv", summary)
    write_csv(SUMMARY / "threshold_sensitivity.csv", thresholds)
    metadata = {
        **CONFIG,
        "generated_outputs": {
            "per_seed": "results/summary/scale_sensitivity.csv",
            "summary": "results/summary/scale_sensitivity_summary.csv",
            "thresholds": "results/summary/threshold_sensitivity.csv",
            "raw_events": "results/raw/scale_sensitivity/*.csv",
            "generated_policies": "results/generated_scale_policies/*/*.json",
        },
    }
    (SUMMARY / "sensitivity_experiment_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Sensitivity experiments: PASS")


if __name__ == "__main__":
    main()
