from __future__ import annotations
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def rules(name: str):
    data = json.loads((ROOT / "datasets/examples" / name).read_text())
    return {(r["subject"], r["action"], r["resource"]) for r in data["allow"]}

class SORSemanticsTest(unittest.TestCase):
    def test_policy_relationships(self):
        stable = rules("policy_stable.json")
        required = rules("policy_required.json")
        over_aggressive = rules("policy_candidate_over_aggressive.json")
        lower_risk = rules("policy_candidate_lower_risk.json")
        self.assertEqual(len(stable), 8)
        self.assertEqual(len(required), 7)
        self.assertTrue(required < stable)
        self.assertEqual(len(stable - required), 1)
        self.assertEqual(lower_risk, required)
        self.assertEqual(len(stable - over_aggressive), 3)
        self.assertGreater(len(required - over_aggressive), 0)

    def test_trace_exercises_redundant_tuple(self):
        stable = rules("policy_stable.json")
        required = rules("policy_required.json")
        redundant = stable - required
        trace = json.loads((ROOT / "datasets/examples/replay_trace.json").read_text())
        tuples = {(r["subject"], r["action"], r["resource"]) for r in trace}
        self.assertTrue(redundant <= tuples)

    def test_sensitivity_configuration(self):
        cfg = json.loads((ROOT / "config/sensitivity_experiments.json").read_text())
        self.assertEqual(cfg["seeds"], [2026, 2027, 2028])
        self.assertEqual(cfg["requests_per_seed"], 50000)
        self.assertEqual(
            [(s["identities"], s["stable_entitlements"], s["required_entitlements"]) for s in cfg["scales"]],
            [(4, 8, 7), (100, 500, 450), (1000, 5000, 4500)],
        )
        self.assertAlmostEqual(sum(cfg["generated_request_mix"].values()), 1.0)
        self.assertEqual(cfg["threshold_values"], [0.005, 0.01, 0.03, 0.05, 0.10])


if __name__ == "__main__":
    unittest.main()
