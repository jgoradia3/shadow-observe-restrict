# Optional Public-Source Extraction Path

## Purpose

This optional path applies the reference implementation's static extraction and generated-replay
pipeline to authorization structures obtained from selected public cloud-native
repositories.

It provides external grounding for authorization structure and permission
shape. It is not a production workload evaluation or a separate source of
production workload labels.

## Supported inputs

The extraction pipeline recognizes selected authorization-related structures
from:

- Kubernetes RBAC YAML or YML files;
- GitHub Actions workflow permission declarations;
- Rego policy files.

The recorded source repositories and provenance information are listed in:

```text
datasets/metadata/public_sources.csv
```

## Reproduction

This path requires network access.

Fetch the recorded sources:

```bash
bash scripts/fetch_public_sources.sh
```

Extract supported configuration files:

```bash
python3 scripts/extract_public_policy_configs.py
```

Run the public-source-derived workload path:

```bash
bash scripts/run_all.sh --public
```

The default deterministic reproduction path remains:

```bash
bash scripts/run_all.sh
```

The explicit `--public` mode does not silently fall back to local examples. If
extracted public inputs are missing, it exits before deleting or replacing
previously generated outputs.

## Generated outputs

The public-source path produces or updates:

```text
datasets/derived_graphs/public_policy.json
datasets/derived_graphs/public_trace.json
datasets/derived_graphs/workload_origin.txt
results/raw/public_policy_events.csv
reference implementation_results/public_policy_workload_metrics.csv
reference implementation_results/public_source_extraction_metrics.json
```

## Interpretation

The extracted configurations provide authorization subjects, resources,
actions, roles, bindings, and permission relationships. The experiment then
constructs a generated replay over those extracted structures and applies the
same SOR rollout mechanisms.

The resulting request sequence remains generated. Public repositories generally
do not provide production authorization-request logs or reliable ground-truth
labels identifying every permission required by a real business workflow.

Therefore, this path provides:

- external authorization-structure grounding;
- inspectable source provenance;
- reproducible static extraction;
- a generated replay over extracted structures.

It does not provide:

- production request frequencies;
- enterprise identity ownership;
- human-validated business-critical labels;
- incident-driven or seasonal access behavior;
- customer or employer telemetry;
- evidence of production authorization effectiveness.
