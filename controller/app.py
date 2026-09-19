import json, os, time
from pathlib import Path
from threading import Lock
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="SOR Rollout Controller")
lock = Lock()
stable_path = Path(os.getenv("SOR_STABLE_POLICY", "datasets/examples/policy_stable.json"))
candidate_path = Path(os.getenv("SOR_CANDIDATE_POLICY", "datasets/examples/policy_candidate_over_aggressive.json"))
threshold = float(os.getenv("SOR_MISMATCH_THRESHOLD", "0.03"))
min_events = int(os.getenv("SOR_MIN_EVENTS", "20"))
with open(stable_path) as f: stable_policy = json.load(f)
with open(candidate_path) as f: candidate_policy = json.load(f)

state = {
    "mode": "stable",  # stable, shadow, restricted, promotion_withheld, rollback
    "active_version": stable_policy["version"],
    "stable_version": stable_policy["version"],
    "candidate_version": candidate_policy["version"],
    "rollout_started_at": None,
    "promotion_withheld_at": None,
    "rollback_triggered_at": None,
    "events": 0,
    "mismatches": 0,
    "safety_reason": None,
}
node_versions = {}

class NodeReport(BaseModel):
    node_id: str; version: str; mode: str; timestamp: float | None = None
class AggregateReport(BaseModel):
    events: int; mismatches: int

@app.get("/health")
def health(): return {"ok": True, "state": state}

@app.post("/rollout/start")
def start_rollout():
    with lock:
        state.update({"mode":"shadow", "active_version":stable_policy["version"],
                      "rollout_started_at":time.time(), "promotion_withheld_at":None,
                      "rollback_triggered_at":None, "events":0, "mismatches":0,
                      "safety_reason":None})
    return state

@app.post("/rollout/restrict")
def restrict():
    with lock:
        if state["mode"] == "shadow":
            state["mode"] = "restricted"
            state["active_version"] = candidate_policy["version"]
    return state

@app.post("/rollout/rollback")
def rollback(reason: dict | None = None):
    with lock:
        state.update({"mode":"rollback", "active_version":stable_policy["version"],
                      "rollback_triggered_at":time.time(),
                      "safety_reason":(reason or {}).get("reason", "manual")})
    return state

@app.get("/policy/latest")
def latest_policy():
    with lock:
        return {"mode":state["mode"], "stable_policy":stable_policy,
                "candidate_policy":candidate_policy, "controller_state":state}

@app.post("/nodes/report")
def report_node(r: NodeReport):
    with lock:
        node_versions[r.node_id] = {"version":r.version, "mode":r.mode,
                                    "timestamp":r.timestamp or time.time()}
    return {"ok":True, "nodes":node_versions}

@app.get("/nodes")
def nodes(): return node_versions

@app.post("/telemetry/aggregate")
def aggregate(report: AggregateReport):
    with lock:
        state["events"] += report.events
        state["mismatches"] += report.mismatches
        rate = state["mismatches"] / max(state["events"], 1)
        if state["mode"] == "shadow" and state["events"] >= min_events and rate > threshold:
            state.update({"mode":"promotion_withheld", "active_version":stable_policy["version"],
                          "promotion_withheld_at":time.time(),
                          "safety_reason":f"mismatch_rate={rate:.3f} threshold={threshold}"})
        elif state["mode"] == "restricted" and state["events"] >= min_events and rate > threshold:
            state.update({"mode":"rollback", "active_version":stable_policy["version"],
                          "rollback_triggered_at":time.time(),
                          "safety_reason":f"mismatch_rate={rate:.3f} threshold={threshold}"})
    return {"ok":True, "state":state, "mismatch_rate":state["mismatches"]/max(state["events"],1)}
