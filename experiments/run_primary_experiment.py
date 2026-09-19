#!/usr/bin/env python3
"""Generate the primary controlled SOR replay results.

The effective stable policy and the generator-defined required-policy oracle are separate. Two candidates
are evaluated over the same replay:
  * over-aggressive: removes permissions exercised by required synthetic requests;
  * lower-risk: removes only an entitlement excluded from the required-policy set.

All aggregate CSV rows are derived from request-level events.
The script is intended as supporting reproducibility material for the public reference implementation.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "results" / "summary"
RAW = ROOT / "results" / "raw"
SUMMARY.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

DEFAULT_SEED = 2026
DEFAULT_REQUESTS = 50_000
OBSERVATION_PREFIX_FRACTION = 0.20
MIN_GATE_OBSERVATIONS = 20
MISMATCH_RATE_THRESHOLD = 0.03
LEGITIMATE_DENIAL_THRESHOLD = 0
CANDIDATE_EXPANSION_THRESHOLD = 0


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    path: Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rule_set(policy: dict) -> set[tuple[str, str, str]]:
    return {(r["subject"], r["action"], r["resource"]) for r in policy.get("allow", [])}


def expand_and_sample(trace: list[dict], n: int, seed: int) -> list[dict]:
    population: list[dict] = []
    for item in trace:
        clean = {k: v for k, v in item.items() if k != "weight"}
        population.extend([clean] * int(item.get("weight", 1)))
    if not population:
        raise ValueError("replay trace is empty")
    rng = random.Random(seed)
    return [dict(rng.choice(population)) for _ in range(n)]


def evaluate_request(req: dict, stable: set, required: set, candidate: set) -> dict:
    key = (req["subject"], req["action"], req["resource"])
    stable_allow = key in stable
    candidate_allow = key in candidate
    return {
        **req,
        "stable_allow": stable_allow,
        "candidate_allow": candidate_allow,
        "oracle_required": key in required,
        "mismatch": stable_allow != candidate_allow,
        "candidate_would_deny_required": (key in required) and not candidate_allow,
        "candidate_expansion": (not stable_allow) and candidate_allow,
    }


def proposed_reduction_pct(stable: set, candidate: set) -> float:
    return 0.0 if not stable else 100.0 * len(stable - candidate) / len(stable)


def gate_result(observation: list[dict]) -> tuple[bool, dict]:
    mismatch_count = sum(int(e["mismatch"]) for e in observation)
    would_deny = sum(int(e["candidate_would_deny_required"]) for e in observation)
    expansions = sum(int(e["candidate_expansion"]) for e in observation)
    mismatch_rate = mismatch_count / len(observation) if observation else 0.0
    passes = (
        len(observation) >= MIN_GATE_OBSERVATIONS
        and mismatch_rate <= MISMATCH_RATE_THRESHOLD
        and would_deny <= LEGITIMATE_DENIAL_THRESHOLD
        and expansions <= CANDIDATE_EXPANSION_THRESHOLD
    )
    return passes, {
        "observation_requests": len(observation),
        "observation_mismatches": mismatch_count,
        "observation_mismatch_rate": mismatch_rate,
        "observation_required_would_deny": would_deny,
        "observation_expansions": expansions,
    }


def mode_specifications(evals: list[dict]) -> list[dict]:
    n = len(evals)
    observation_end = max(MIN_GATE_OBSERVATIONS, round(n * OBSERVATION_PREFIX_FRACTION))
    observation = evals[:observation_end]
    gate_passed, gate_metrics = gate_result(observation)
    return [
        {
            "Approach": "Immediate enforcement",
            "enforce_from": 0,
            "candidate_enforced": True,
            "Safety Action": "None",
            "gate_passed": None,
            **gate_metrics,
        },
        {
            "Approach": "Shadow-only validation",
            "enforce_from": n,
            "candidate_enforced": False,
            "Safety Action": "Shadow only",
            "gate_passed": None,
            **gate_metrics,
        },
        {
            "Approach": "SOR without rollback",
            "enforce_from": observation_end,
            "candidate_enforced": True,
            "Safety Action": "None",
            "gate_passed": None,
            **gate_metrics,
        },
        {
            "Approach": "Full SOR",
            "enforce_from": observation_end if gate_passed else n,
            "candidate_enforced": gate_passed,
            "Safety Action": "Promoted" if gate_passed else "Promotion withheld",
            "gate_passed": gate_passed,
            **gate_metrics,
        },
    ]


def aggregate_rows(candidate: Candidate, evals: list[dict], stable: set, candidate_rules: set) -> tuple[list[dict], list[dict]]:
    n = len(evals)
    proposed = proposed_reduction_pct(stable, candidate_rules)
    mismatches = sum(int(e["mismatch"]) for e in evals)
    rows: list[dict] = []
    raw_rows: list[dict] = []

    for spec in mode_specifications(evals):
        legitimate_denials = 0
        affected: set[str] = set()
        for idx, e in enumerate(evals):
            in_observation = idx < round(n * OBSERVATION_PREFIX_FRACTION)
            enforce_candidate = spec["candidate_enforced"] and idx >= spec["enforce_from"]
            enforced_allow = e["candidate_allow"] if enforce_candidate else e["stable_allow"]
            legitimate_denial = bool(e["oracle_required"] and not enforced_allow)
            if legitimate_denial:
                legitimate_denials += 1
                affected.add(e["subject"])
            raw_rows.append({
                "request_id": f"replay-{idx + 1:06d}",
                "candidate": candidate.key,
                "candidate_label": candidate.label,
                "approach": spec["Approach"],
                "phase": "observation" if in_observation else "post-observation",
                "subject": e["subject"],
                "action": e["action"],
                "resource": e["resource"],
                "expected_rare": e.get("expected_rare", False),
                "stable_decision": "allow" if e["stable_allow"] else "deny",
                "candidate_decision": "allow" if e["candidate_allow"] else "deny",
                "enforced_decision": "allow" if enforced_allow else "deny",
                "oracle_required": e["oracle_required"],
                "mismatch": e["mismatch"],
                "candidate_would_deny_required": e["candidate_would_deny_required"],
                "legitimate_denial": legitimate_denial,
                "safety_action": spec["Safety Action"],
            })

        enforced_reduction = proposed if spec["candidate_enforced"] else 0.0
        rows.append({
            "Candidate": candidate.label,
            "Approach": spec["Approach"],
            "Proposed Reduction %": f"{proposed:.1f}",
            "Enforced Reduction %": f"{enforced_reduction:.1f}",
            "Legitimate Denials": legitimate_denials,
            "LDR": f"{legitimate_denials / n:.8g}",
            "Affected IDs": len(affected),
            "Mismatches": mismatches,
            "Safety Action": spec["Safety Action"],
        })
    return rows, raw_rows


def prefix_rows(candidate: Candidate, evals: list[dict]) -> list[dict]:
    n = len(evals)
    prefixes = [("7.1%", 1 / 14), ("21.4%", 3 / 14), ("50.0%", 1 / 2), ("100.0%", 1.0)]
    rows = []
    for label, fraction in prefixes:
        count = max(1, round(n * fraction))
        subset = evals[:count]
        mismatches = sum(int(e["mismatch"]) for e in subset)
        would_deny = sum(int(e["candidate_would_deny_required"]) for e in subset)
        affected = {e["subject"] for e in subset if e["candidate_would_deny_required"]}
        rows.append({
            "Candidate": candidate.label,
            "Replay Prefix": label,
            "Agreement S": f"{1 - mismatches / count:.6f}",
            "Mismatches": mismatches,
            "Candidate Would-Deny": would_deny,
            "Candidate LDR": f"{would_deny / count:.8g}",
            "Candidate-Affected IDs": len(affected),
            "Request Count": count,
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_raw(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    write_csv(path, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    stable = rule_set(load_json(ROOT / "datasets/examples/policy_stable.json"))
    required = rule_set(load_json(ROOT / "datasets/examples/policy_required.json"))
    candidates = [
        Candidate("over_aggressive", "Over-aggressive candidate", ROOT / "datasets/examples/policy_candidate_over_aggressive.json"),
        Candidate("lower_risk", "Lower-risk candidate", ROOT / "datasets/examples/policy_candidate_lower_risk.json"),
    ]
    trace = load_json(ROOT / "datasets/examples/replay_trace.json")
    requests = expand_and_sample(trace, args.requests, args.seed)

    comparison_rows: list[dict] = []
    prefix_results: list[dict] = []
    raw_rows: list[dict] = []
    candidate_metadata: dict[str, dict] = {}

    for candidate in candidates:
        rules = rule_set(load_json(candidate.path))
        evals = [evaluate_request(req, stable, required, rules) for req in requests]
        comparison, mode_raw = aggregate_rows(candidate, evals, stable, rules)
        comparison_rows.extend(comparison)
        prefix_results.extend(prefix_rows(candidate, evals))
        raw_rows.extend(mode_raw)
        gate_passed, gate_metrics = gate_result(evals[:round(args.requests * OBSERVATION_PREFIX_FRACTION)])
        candidate_metadata[candidate.key] = {
            "label": candidate.label,
            "policy_file": str(candidate.path.relative_to(ROOT)),
            "entitlements": len(rules),
            "removed_entitlements": len(stable - rules),
            "proposed_reduction_percent": proposed_reduction_pct(stable, rules),
            "full_sor_gate_passed": gate_passed,
            "gate_metrics": gate_metrics,
        }

    write_csv(SUMMARY / "baseline_comparison.csv", comparison_rows)
    write_csv(SUMMARY / "replay_prefix_sensitivity.csv", prefix_results)
    write_raw(RAW / "primary_replay_events.csv", raw_rows)

    obsolete = SUMMARY / "observation_window_sensitivity.csv"
    if obsolete.exists():
        obsolete.unlink()

    metadata = {
        "seed": args.seed,
        "request_count": args.requests,
        "sampling": "deterministic weighted draws using random.Random; no independence claim",
        "single_run": True,
        "synthetic": True,
        "oracle": "required-v1 generator-defined required subject/action/resource allow-list",
        "stable_policy_file": "datasets/examples/policy_stable.json",
        "required_policy_file": "datasets/examples/policy_required.json",
        "stable_entitlements": len(stable),
        "required_entitlements": len(required),
        "generator_labeled_redundant_entitlements": len(stable - required),
        "thresholds": {
            "observation_prefix_fraction": OBSERVATION_PREFIX_FRACTION,
            "observation_prefix_requests": round(args.requests * OBSERVATION_PREFIX_FRACTION),
            "minimum_gate_observations": MIN_GATE_OBSERVATIONS,
            "mismatch_rate_threshold": MISMATCH_RATE_THRESHOLD,
            "legitimate_denial_threshold": LEGITIMATE_DENIAL_THRESHOLD,
            "candidate_expansion_threshold": CANDIDATE_EXPANSION_THRESHOLD,
        },
        "candidates": candidate_metadata,
        "metric_definitions": {
            "LDR": "enforced legitimate denials divided by all replay requests",
            "candidate_LDR": "required requests the candidate would deny divided by requests in the replay prefix",
            "mismatch": "stable and candidate decisions differ",
            "affected_IDs": "distinct subjects with enforced legitimate denials",
            "oracle_required": "membership in required-v1, not membership in the effective stable policy",
        },
    }
    (SUMMARY / "primary_experiment_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"comparison": comparison_rows, "prefix": prefix_results, "metadata": metadata}, indent=2))


if __name__ == "__main__":
    main()
