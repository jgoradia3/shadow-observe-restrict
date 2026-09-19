import argparse, json, yaml
from pathlib import Path

def parse(path):
    y = yaml.safe_load(Path(path).read_text())
    workflow = y.get("name", Path(path).stem)
    perms = y.get("permissions", {}) or {}
    edges = []
    if isinstance(perms, str):
        edges.append({"subject":f"gha:{workflow}","action":perms,"resource":"github:*","source":"github-actions"})
    else:
        for scope, level in perms.items():
            edges.append({"subject":f"gha:{workflow}","action":level,"resource":f"github:{scope}","source":"github-actions"})
    return edges

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("path"); p.add_argument("--out", default="datasets/derived_graphs/gha_edges.json")
    a=p.parse_args(); edges=parse(a.path); Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(edges, indent=2)); print(json.dumps({"edges":len(edges),"out":a.out}, indent=2))
