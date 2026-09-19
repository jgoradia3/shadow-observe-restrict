import argparse, json, yaml
from pathlib import Path

def parse(path):
    docs = list(yaml.safe_load_all(Path(path).read_text()))
    roles, bindings, edges = {}, [], []
    for d in docs:
        if not d: continue
        kind = d.get("kind")
        meta = d.get("metadata", {})
        ns = meta.get("namespace", "default")
        name = meta.get("name")
        if kind in ["Role", "ClusterRole"]:
            roles[(kind, name, ns)] = d.get("rules", [])
        elif kind in ["RoleBinding", "ClusterRoleBinding"]:
            bindings.append(d)
    for b in bindings:
        ns = b.get("metadata", {}).get("namespace", "default")
        ref = b.get("roleRef", {})
        rules = roles.get((ref.get("kind"), ref.get("name"), ns), []) or roles.get((ref.get("kind"), ref.get("name"), "default"), [])
        for s in b.get("subjects", []):
            subject = s.get("name")
            for rule in rules:
                for res in rule.get("resources", []):
                    for verb in rule.get("verbs", []):
                        edges.append({"subject":subject,"action":verb,"resource":f"k8s:{ns}:{res}","source":"kubernetes-rbac"})
    return edges

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("path"); p.add_argument("--out", default="datasets/derived_graphs/rbac_edges.json")
    a=p.parse_args(); edges=parse(a.path); Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(edges, indent=2)); print(json.dumps({"edges":len(edges),"out":a.out}, indent=2))
