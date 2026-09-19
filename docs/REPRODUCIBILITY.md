# Reproducibility

## Environment

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

## Quick demonstration

```bash
python3 examples/run_demo.py
```

## Primary controlled replay

```bash
python3 experiments/run_primary_experiment.py --requests 50000 --seed 2026
```

This produces:

- `results/summary/baseline_comparison.csv`
- `results/summary/replay_prefix_sensitivity.csv`
- `results/summary/primary_experiment_metadata.json`
- `results/raw/primary_replay_events.csv`

The committed repository includes the aggregate summary files but not the large generated request-level CSV.

## Threshold and scale sensitivity

```bash
python3 experiments/run_sensitivity_experiments.py
```

These experiments are supporting reproducibility material and are not needed to understand the practitioner article.

## Distributed propagation example

```bash
python3 experiments/simulate_distributed_run.py
python3 experiments/make_supporting_figures.py
```

## Validation

After generating the full results, run:

```bash
python3 experiments/validate_results.py
```

The validator recomputes aggregate values from the generated request-level outputs and checks policy-set relationships.

## Complete path

```bash
bash scripts/run_all.sh
```

The default complete path is deterministic and does not require Docker, cloud credentials, or proprietary data.

## Optional paths

```bash
bash scripts/run_docker_demo.sh
python3 experiments/benchmark_runtime.py
```

The Docker demonstration and host-specific benchmark are diagnostic only. They are not used as evidence of production performance.
