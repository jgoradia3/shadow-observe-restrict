import json, random, argparse

def generate(policy_path, out_path, rare_fraction=0.15):
    with open(policy_path) as f: policy = json.load(f)
    rules = policy["allow"]
    rare_n = max(1, int(len(rules) * rare_fraction))
    rare_idx = set(random.sample(range(len(rules)), rare_n))
    trace = []
    for i, r in enumerate(rules):
        rare = i in rare_idx
        trace.append({**r, "weight": 2 if rare else 20, "expected_rare": rare})
    with open(out_path, "w") as f: json.dump(trace, f, indent=2)
    print(f"wrote {out_path} with {len(trace)} operations")

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--policy", required=True); p.add_argument("--out", required=True); p.add_argument("--rare-fraction", type=float, default=0.15)
    a=p.parse_args(); generate(a.policy, a.out, a.rare_fraction)
