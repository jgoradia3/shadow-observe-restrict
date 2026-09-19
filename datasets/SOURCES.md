# Dataset sources

The repository supports two workload modes.

## Local synthetic examples

Files under `datasets/examples/` are small synthetic policies and request templates included so the reference implementation can be run offline. They do not represent production enterprise traffic.

## Optional public configuration structures

Selected public repositories are recorded in `datasets/metadata/public_sources.csv`. The fetch/extraction utilities inspect configuration and policy structures only; they do not execute third-party code and do not provide production request frequencies, temporal dependencies, or business semantics.

Use:

```bash
bash scripts/fetch_public_sources.sh
python3 scripts/extract_public_policy_configs.py
bash scripts/run_all.sh --public
```

See `docs/PUBLIC_CONFIG_EXAMPLE.md` for interpretation limits.
