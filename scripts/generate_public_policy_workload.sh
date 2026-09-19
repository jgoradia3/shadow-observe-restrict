#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p datasets/derived_graphs results/summary

MODE="example"
if [[ "${1:-}" == "--public" ]]; then
  MODE="public"
fi

if [[ "$MODE" == "public" ]]; then
  if [[ ! -d datasets/public_sources/extracted ]] || [[ -z "$(find datasets/public_sources/extracted -type f \( -name '*.yaml' -o -name '*.yml' -o -name '*.rego' \) 2>/dev/null | head -1)" ]]; then
    echo "No extracted public sources found. Run:"
    echo "  bash scripts/fetch_public_sources.sh"
    echo "  python3 scripts/extract_public_policy_configs.py"
    exit 1
  fi
  python3 scripts/build_public_policy_workload.py
  echo "public" > datasets/derived_graphs/workload_origin.txt
else
  python3 -m parsers.rbac_parser datasets/examples/k8s_rbac_sample.yaml --out datasets/derived_graphs/rbac_edges.json
  python3 -m parsers.ghactions_parser datasets/examples/github_actions_sample.yml --out datasets/derived_graphs/gha_edges.json
  python3 -m parsers.graph_builder datasets/derived_graphs/rbac_edges.json datasets/derived_graphs/gha_edges.json --policy datasets/derived_graphs/public_policy.json --trace datasets/derived_graphs/public_trace.json
  cat > results/summary/public_source_extraction_metrics.json <<'JSON'
{
  "mode": "example-fallback",
  "claim_scope": "local cloud-native configuration examples; not public corpus",
  "note": "Run bash scripts/fetch_public_sources.sh, python3 scripts/extract_public_policy_configs.py, and bash scripts/run_all.sh --public to derive workloads from public repositories."
}
JSON
  echo "example-fallback" > datasets/derived_graphs/workload_origin.txt
fi
