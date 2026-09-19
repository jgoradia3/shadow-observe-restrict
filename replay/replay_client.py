import argparse, json, random, time, requests
from itertools import cycle


def load_trace(path):
    with open(path) as f:
        trace = json.load(f)
    expanded = []
    for item in trace:
        expanded.extend([item] * int(item.get("weight", 1)))
    random.seed(7)
    random.shuffle(expanded)
    return expanded


def send(node, payload):
    r = requests.post(f"{node}/authorize", json=payload, timeout=5)
    return r.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--nodes", required=True, help="Comma-separated auth node URLs")
    p.add_argument("--trace", required=True)
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--sleep-ms", type=int, default=25)
    p.add_argument("--fanout", action="store_true", help="Send each logical request to all nodes to measure enforcement divergence")
    args = p.parse_args()

    nodes = [n.strip() for n in args.nodes.split(",") if n.strip()]
    trace = load_trace(args.trace)
    logical_id = 0
    sent = 0
    results = []

    for _ in range(args.rounds):
        for req in trace:
            logical_id += 1
            logical_request_id = f"logical-{logical_id:06d}"
            payload_base = {k: req[k] for k in ["subject", "action", "resource"]}
            payload_base["expected_rare"] = bool(req.get("expected_rare", False))
            payload_base["logical_request_id"] = logical_request_id

            target_nodes = nodes if args.fanout else [nodes[(logical_id - 1) % len(nodes)]]
            for node in target_nodes:
                sent += 1
                payload = dict(payload_base)
                payload["request_id"] = f"{logical_request_id}:{node.rsplit(':', 1)[-1]}"
                try:
                    results.append(send(node, payload))
                except Exception as e:
                    results.append({"request_id": payload["request_id"], "logical_request_id": logical_request_id, "node": node, "error": str(e)})
            time.sleep(args.sleep_ms / 1000)
    print(json.dumps({"logical_requests": logical_id, "sent": sent, "responses": len(results), "fanout": args.fanout}, indent=2))


if __name__ == "__main__":
    main()
