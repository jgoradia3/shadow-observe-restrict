#!/usr/bin/env python3
"""Build SOR replay workload from extracted public authorization configs.

Input: datasets/public_sources/extracted/* containing statically extracted YAML/YML/Rego files.
Output: datasets/derived_graphs/public_policy.json and public_trace.json.
"""
import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
K8S_KINDS = {"Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"}


def parse_k8s_file(path: Path, source_id: str):
    edges = []
    try:
        docs = list(yaml.safe_load_all(path.read_text(errors="ignore")))
    except Exception:
        return edges
    roles = {}
    bindings = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        kind = d.get("kind")
        meta = d.get("metadata", {}) or {}
        ns = meta.get("namespace", "default")
        name = meta.get("name")
        if not name:
            continue
        if kind in {"Role", "ClusterRole"}:
            roles[(kind, name, ns)] = d.get("rules", []) or []
            if kind == "ClusterRole":
                roles[(kind, name, "default")] = d.get("rules", []) or []
        elif kind in {"RoleBinding", "ClusterRoleBinding"}:
            bindings.append(d)
    for b in bindings:
        ns = (b.get("metadata", {}) or {}).get("namespace", "default")
        ref = b.get("roleRef", {}) or {}
        rules = roles.get((ref.get("kind"), ref.get("name"), ns), []) or roles.get((ref.get("kind"), ref.get("name"), "default"), [])
        for s in b.get("subjects", []) or []:
            subject = s.get("name") or "unknown-subject"
            subject_kind = s.get("kind", "Subject")
            for rule in rules:
                for res in rule.get("resources", []) or ["*"]:
                    for verb in rule.get("verbs", []) or ["*"]:
                        edges.append({
                            "subject": f"{source_id}:{subject_kind}:{subject}",
                            "action": str(verb),
                            "resource": f"k8s:{ns}:{res}",
                            "source": source_id,
                            "source_type": "kubernetes-rbac",
                            "file": str(path),
                        })
    return edges


def parse_github_workflow(path: Path, source_id: str):
    edges = []
    try:
        y = yaml.safe_load(path.read_text(errors="ignore")) or {}
    except Exception:
        return edges
    if not isinstance(y, dict):
        return edges
    workflow = y.get("name") or path.stem
    perms = y.get("permissions", {}) or {}
    if isinstance(perms, str):
        edges.append({
            "subject": f"{source_id}:gha:{workflow}",
            "action": perms,
            "resource": "github:*",
            "source": source_id,
            "source_type": "github-actions",
            "file": str(path),
        })
    elif isinstance(perms, dict):
        for scope, level in perms.items():
            edges.append({
                "subject": f"{source_id}:gha:{workflow}",
                "action": str(level),
                "resource": f"github:{scope}",
                "source": source_id,
                "source_type": "github-actions",
                "file": str(path),
            })
    return edges


def parse_rego(path: Path, source_id: str):
    text = path.read_text(errors="ignore")
    pkg_match = re.search(r"^package\s+([\w.]+)", text, re.MULTILINE)
    package = pkg_match.group(1) if pkg_match else path.stem
    # Static approximation: each allow/deny/violation rule becomes a policy-condition edge.
    rule_names = sorted(set(re.findall(r"^\s*(allow|deny|violation|warn)\b", text, re.MULTILINE)))
    edges = []
    for rule in rule_names:
        edges.append({
            "subject": f"{source_id}:rego:{package}",
            "action": rule,
            "resource": f"rego:{package}",
            "source": source_id,
            "source_type": "rego-policy",
            "file": str(path),
        })
    return edges


def is_workflow(path: Path):
    return ".github" in path.parts and "workflows" in path.parts and path.suffix in {".yml", ".yaml"}


def build_edges(extracted: Path):
    edges = []
    for source_dir in sorted([p for p in extracted.iterdir() if p.is_dir()]):
        source_id = source_dir.name
        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix == ".rego":
                edges.extend(parse_rego(path, source_id))
            elif path.suffix in {".yml", ".yaml"}:
                if is_workflow(path):
                    edges.extend(parse_github_workflow(path, source_id))
                else:
                    edges.extend(parse_k8s_file(path, source_id))
    # De-duplicate while preserving provenance count in separate metadata.
    seen = set()
    deduped = []
    for e in edges:
        key = (e["subject"], e["action"], e["resource"], e["source_type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def build_policy_trace(edges, policy_out: Path, trace_out: Path, metrics_out: Path):
    allow = [{"subject": e["subject"], "action": e["action"], "resource": e["resource"]} for e in edges]
    policy = {
        "version": "public-config-derived-v1",
        "description": "Policy generated from statically extracted public cloud-native authorization configuration structures.",
        "claim_scope": "configuration-structure-derived; not production telemetry",
        "allow": allow,
    }
    trace = []
    for i, e in enumerate(allow):
        # Long-tail pattern: frequent service paths plus low-frequency/dormant candidates.
        rare = (i % 7 == 0) or ("delete" in e["action"]) or ("write" in e["action"])
        dormant_candidate = rare and (i % 3 == 0)
        trace.append({
            **e,
            "weight": 1 if dormant_candidate else (3 if rare else 20),
            "expected_rare": rare,
            "dormant_candidate": dormant_candidate,
        })
    source_counts = {}
    type_counts = {}
    for e in edges:
        source_counts[e["source"]] = source_counts.get(e["source"], 0) + 1
        type_counts[e["source_type"]] = type_counts.get(e["source_type"], 0) + 1
    metrics = {
        "edges": len(edges),
        "trace_events": len(trace),
        "sources": source_counts,
        "source_types": type_counts,
        "rare_trace_events": sum(1 for t in trace if t["expected_rare"]),
        "dormant_candidate_events": sum(1 for t in trace if t["dormant_candidate"]),
    }
    policy_out.parent.mkdir(parents=True, exist_ok=True)
    policy_out.write_text(json.dumps(policy, indent=2))
    trace_out.write_text(json.dumps(trace, indent=2))
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--extracted", default=str(ROOT / "datasets/public_sources/extracted"))
    p.add_argument("--policy", default=str(ROOT / "datasets/derived_graphs/public_policy.json"))
    p.add_argument("--trace", default=str(ROOT / "datasets/derived_graphs/public_trace.json"))
    p.add_argument("--metrics", default=str(ROOT / "results/summary/public_source_extraction_metrics.json"))
    args = p.parse_args()
    extracted = Path(args.extracted)
    edges = build_edges(extracted) if extracted.exists() else []
    if not edges:
        raise SystemExit("No extracted public config edges found. Run fetch_public_sources.sh and extract_public_policy_configs.py, or use generate_public_policy_workload.sh without --public for the local example fallback.")
    build_policy_trace(edges, Path(args.policy), Path(args.trace), Path(args.metrics))


if __name__ == "__main__":
    main()
