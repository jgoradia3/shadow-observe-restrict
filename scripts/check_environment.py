#!/usr/bin/env python3
"""Fail-fast environment and input check for the offline SOR reproduction path."""
from __future__ import annotations
import importlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 10)
MODULES = {
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "yaml": "PyYAML",
    "requests": "requests",
}
REQUIRED = [
    "datasets/examples/policy_stable.json",
    "datasets/examples/policy_required.json",
    "datasets/examples/policy_candidate_over_aggressive.json",
    "datasets/examples/policy_candidate_lower_risk.json",
    "datasets/examples/replay_trace.json",
    "config/sensitivity_experiments.json",
]


def main() -> None:
    errors: list[str] = []
    if sys.version_info < MIN_PYTHON:
        errors.append(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required; found {platform.python_version()}")
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for module, package in MODULES.items():
        try:
            imported = importlib.import_module(module)
            versions[package] = getattr(imported, "__version__", "installed")
        except Exception as exc:
            errors.append(f"missing dependency {package}: {exc}")
    for rel in REQUIRED:
        p = ROOT / rel
        if not p.is_file():
            errors.append(f"missing required input: {rel}")
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON in {rel}: {exc}")
    if errors:
        print("Environment check: FAIL", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        raise SystemExit(2)
    print("Environment check: PASS")
    print(json.dumps(versions, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
