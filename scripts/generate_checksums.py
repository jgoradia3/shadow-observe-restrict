#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "summary" / "SHA256SUMS.txt"
FILES = [
    ROOT / "results/summary/baseline_comparison.csv",
    ROOT / "results/summary/replay_prefix_sensitivity.csv",
    ROOT / "results/summary/primary_experiment_metadata.json",
    ROOT / "results/summary/delay_sensitivity.csv",
    ROOT / "results/summary/scale_sensitivity.csv",
    ROOT / "results/summary/scale_sensitivity_summary.csv",
    ROOT / "results/summary/threshold_sensitivity.csv",
    ROOT / "results/summary/sensitivity_experiment_metadata.json",
]
lines=[]
for p in FILES:
    if not p.exists():
        continue
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    lines.append(f"{digest}  {p.relative_to(ROOT).as_posix()}")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines)+"\n", encoding="utf-8")
print(f"Wrote {OUT.relative_to(ROOT)}")
