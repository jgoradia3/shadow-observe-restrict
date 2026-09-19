#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")/.."

MODE="--example-fallback"
WITH_BENCHMARK=0
for arg in "$@"; do
  case "$arg" in
    --public) MODE="--public" ;;
    --with-benchmark) WITH_BENCHMARK=1 ;;
    -h|--help)
      cat <<'HELP'
Usage: bash scripts/run_all.sh [--public] [--with-benchmark]

Default: deterministic offline reproduction of the controlled SOR examples.
--public: use previously fetched public configuration inputs.
--with-benchmark: additionally run the host-specific diagnostic benchmark.
Docker is optional and is run separately with bash scripts/run_docker_demo.sh.
HELP
      exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p results/raw results/tables results/figures results/summary results/diagnostics
rm -f results/raw/*.csv results/raw/scale_sensitivity/*.csv results/tables/*.csv results/tables/*.json results/figures/*.png

printf '[1/9] Checking environment and required inputs\n'
python3 scripts/check_environment.py
printf '[2/9] Running semantic unit tests\n'
python3 -m unittest discover -s tests -v
printf '[3/9] Generating configuration-derived example workload (%s)\n' "$MODE"
bash scripts/generate_public_policy_workload.sh "$MODE"
printf '[4/9] Running distributed propagation example\n'
python3 experiments/simulate_distributed_run.py
printf '[5/9] Generating supporting summaries and figures\n'
python3 experiments/make_supporting_figures.py
printf '[6/9] Running primary controlled replay\n'
python3 experiments/run_primary_experiment.py --requests 50000 --seed 2026 >/dev/null
printf '[7/9] Running optional threshold and scale sensitivity\n'
python3 experiments/run_sensitivity_experiments.py
if [[ "$WITH_BENCHMARK" -eq 1 ]]; then
  python3 experiments/benchmark_runtime.py
fi
printf '[8/9] Validating generated results\n'
python3 experiments/validate_results.py
printf '[9/9] Writing checksums for aggregate outputs\n'
python3 scripts/generate_checksums.py

printf '\nSOR reproduction complete. Aggregate outputs are in results/summary/.\n'
