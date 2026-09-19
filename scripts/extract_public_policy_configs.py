#!/usr/bin/env python3
"""Static extractor for public authorization configuration sources.

The extractor copies only policy/configuration artifacts into datasets/public_sources/extracted:
- Kubernetes-ish YAML/YML files containing Role, ClusterRole, RoleBinding, ClusterRoleBinding, or ServiceAccount
- GitHub Actions workflow files under .github/workflows
- Rego files

It does not execute any code from the source repositories.
"""
import csv
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "datasets" / "public_sources" / "raw"
OUT = ROOT / "datasets" / "public_sources" / "extracted"
META = ROOT / "datasets" / "metadata" / "public_sources.csv"
MANIFEST = ROOT / "datasets" / "metadata" / "extracted_files.csv"
K8S_KINDS = {"Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding", "ServiceAccount"}
MAX_FILES_PER_SOURCE = 250


def is_k8s_auth_yaml(path: Path) -> bool:
    try:
        text = path.read_text(errors="ignore")
        docs = list(yaml.safe_load_all(text))
    except Exception:
        return False
    for doc in docs:
        if isinstance(doc, dict) and doc.get("kind") in K8S_KINDS:
            return True
    return False


def is_github_workflow(path: Path) -> bool:
    parts = set(path.parts)
    return ".github" in parts and "workflows" in parts and path.suffix in {".yml", ".yaml"}


def is_rego(path: Path) -> bool:
    return path.suffix == ".rego"


def safe_rel(path: Path, base: Path) -> Path:
    rel = path.relative_to(base)
    return Path(*[p for p in rel.parts if p not in {"..", "."}])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(META.open()))
    manifest = []

    for row in rows:
        sid = row["source_id"]
        src = RAW / sid
        if not src.exists():
            print(f"[skip] {sid}: not fetched")
            continue
        dst_root = OUT / sid
        copied = 0
        candidates = [p for p in src.rglob("*") if p.is_file() and p.suffix in {".yaml", ".yml", ".rego"}]
        for path in candidates:
            kind = None
            if is_github_workflow(path):
                kind = "github_actions_workflow"
            elif is_rego(path):
                kind = "rego_policy"
            elif is_k8s_auth_yaml(path):
                kind = "kubernetes_rbac_yaml"
            if not kind:
                continue
            rel = safe_rel(path, src)
            dst = dst_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            manifest.append({
                "source_id": sid,
                "project": row["project"],
                "type": kind,
                "relative_path": str(rel),
                "repo_url": row["repo_url"],
                "license": row["license"],
            })
            copied += 1
            if copied >= MAX_FILES_PER_SOURCE:
                break
        print(f"[extract] {sid}: {copied} files")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source_id", "project", "type", "relative_path", "repo_url", "license"])
        writer.writeheader()
        writer.writerows(manifest)
    (ROOT / "datasets" / "metadata" / "extracted_files.json").write_text(json.dumps(manifest, indent=2))
    print(f"[done] wrote {MANIFEST} with {len(manifest)} extracted config files")


if __name__ == "__main__":
    main()
