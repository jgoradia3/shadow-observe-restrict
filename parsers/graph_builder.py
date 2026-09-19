import argparse, json
from pathlib import Path

def build(edge_files, out_policy, out_trace):
    edges=[]
    for f in edge_files:
        edges.extend(json.loads(Path(f).read_text()))
    allow=[{"subject":e["subject"],"action":e["action"],"resource":e["resource"]} for e in edges]
    policy={"version":"public-derived-v1","description":"Policy derived from public authorization configuration structures.","allow":allow}
    trace=[]
    for i,e in enumerate(allow):
        rare = i % 5 == 0
        trace.append({**e,"weight":2 if rare else 15,"expected_rare":rare})
    Path(out_policy).write_text(json.dumps(policy, indent=2))
    Path(out_trace).write_text(json.dumps(trace, indent=2))
    print(json.dumps({"edges":len(edges),"policy":out_policy,"trace":out_trace}, indent=2))

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("edges", nargs="+"); p.add_argument("--policy", default="datasets/derived_graphs/public_policy.json"); p.add_argument("--trace", default="datasets/derived_graphs/public_trace.json")
    a=p.parse_args(); build(a.edges, a.policy, a.trace)
