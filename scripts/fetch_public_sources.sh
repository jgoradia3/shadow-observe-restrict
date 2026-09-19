#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

RAW_DIR="datasets/public_sources/raw"
META="datasets/metadata/public_sources.csv"
mkdir -p "$RAW_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to fetch public sources" >&2
  exit 1
fi

python3 - <<'PY'
import csv, subprocess, pathlib, sys
meta = pathlib.Path('datasets/metadata/public_sources.csv')
raw = pathlib.Path('datasets/public_sources/raw')
rows = list(csv.DictReader(meta.open()))
for r in rows:
    dest = raw / r['source_id']
    url = r['repo_url']
    ref = r['default_ref'] or 'main'
    if dest.exists():
        print(f"[skip] {r['source_id']} already exists at {dest}")
        continue
    print(f"[clone] {r['source_id']} <- {url} ({ref})")
    try:
        subprocess.check_call(['git','clone','--depth','1','--branch',ref,url,str(dest)])
    except subprocess.CalledProcessError:
        print(f"[warn] branch {ref} failed for {url}; retrying default branch", file=sys.stderr)
        subprocess.check_call(['git','clone','--depth','1',url,str(dest)])
print('[done] public sources fetched')
PY
