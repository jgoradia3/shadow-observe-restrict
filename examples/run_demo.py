#!/usr/bin/env python3
"""Small practitioner-facing SOR demonstration.

Uses the committed synthetic policies and a deterministic replay to show how
an over-aggressive candidate can be withheld while a lower-risk candidate can
pass the same example gate. This is a mechanism demonstration, not production
validation.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets" / "examples"
OBSERVATION_FRACTION = 0.20
MISMATCH_THRESHOLD = 0.03
MIN_EVENTS = 20


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def rules(policy: dict) -> set[tuple[str, str, str]]:
    return {(r["subject"], r["action"], r["resource"]) for r in policy["allow"]}


def requests(n: int = 5000, seed: int = 2026) -> list[dict]:
    population = []
    for item in load("replay_trace.json"):
        clean = {k: v for k, v in item.items() if k != "weight"}
        population.extend([clean] * int(item.get("weight", 1)))
    rng = random.Random(seed)
    return [dict(rng.choice(population)) for _ in range(n)]


def evaluate(candidate_file: str, label: str) -> None:
    stable = rules(load("policy_stable.json"))
    required = rules(load("policy_required.json"))
    candidate = rules(load(candidate_file))
    replay = requests()
    obs_n = max(MIN_EVENTS, round(len(replay) * OBSERVATION_FRACTION))
    observation = replay[:obs_n]

    mismatches = 0
    required_conflicts = 0
    expansions = 0
    for req in observation:
        key = (req["subject"], req["action"], req["resource"])
        stable_allow = key in stable
        candidate_allow = key in candidate
        mismatches += int(stable_allow != candidate_allow)
        required_conflicts += int(key in required and not candidate_allow)
        expansions += int((not stable_allow) and candidate_allow)

    rate = mismatches / obs_n
    passes = rate <= MISMATCH_THRESHOLD and required_conflicts == 0 and expansions == 0

    print(f"Candidate: {label}")
    print(f"Observed requests: {obs_n}")
    print(f"Policy differences: {mismatches} ({rate:.2%})")
    print(f"Required-access conflicts: {required_conflicts}")
    print(f"Unexpected expansions: {expansions}")
    print(f"Promotion decision: {'PROMOTE' if passes else 'WITHHOLD'}")
    if passes:
        print("Reason: configured promotion criteria satisfied")
    elif required_conflicts:
        print("Reason: required-access conflicts observed")
    elif expansions:
        print("Reason: unexpected permission expansion observed")
    else:
        print("Reason: mismatch threshold exceeded")
    print()


def main() -> None:
    print("Shadow–Observe–Restrict quick demonstration")
    print("Synthetic workload; mechanism illustration only.\n")
    evaluate("policy_candidate_over_aggressive.json", "over-aggressive")
    evaluate("policy_candidate_lower_risk.json", "lower-risk")


if __name__ == "__main__":
    main()
