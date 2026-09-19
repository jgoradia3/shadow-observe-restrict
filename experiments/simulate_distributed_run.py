#!/usr/bin/env python3
"""Deterministic event-driven distributed SOR shadow-evaluation simulation.

Three nodes receive a candidate evaluator after configurable propagation delays.
The stable policy remains enforced during shadow mode. Mismatches are computed
by direct stable/candidate decision comparison. When the aggregate mismatch rate
exceeds the predeclared threshold after the minimum event count, the controller
withholds the candidate and propagates a return-to-stable evaluator to all nodes.
"""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "raw"
TABLES = ROOT / "results" / "tables"
RAW.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "ts","node_id","request_id","logical_request_id","subject","action","resource",
    "node_mode","mode","controller_mode","evaluator_version","policy_version","stable_decision","candidate_decision","decision",
    "enforced_decision","enforced","mismatch","oracle_required","expected_rare","withhold_triggered","rollback_triggered",
    "stale_candidate_evaluator","stale_candidate","telemetry_ingest_lag_ms","propagation_delay_ms"
]
THRESHOLD = 0.03
MIN_EVENTS = 20
REACTION_DELAY_MS = 500
DEFAULT_PROPAGATION_DELAY_MS = 3000
DEFAULT_LOGICAL_EVENTS = 400
SENSITIVITY_DELAYS_MS = [500, 3000, 7000]
TIME_STEP = 0.05


def load_json(rel):
    return json.loads((ROOT / rel).read_text())


def rules(policy):
    return {(r["subject"], r["action"], r["resource"]) for r in policy.get("allow", [])}


def allowed(rule_set, req):
    return (req["subject"], req["action"], req["resource"]) in rule_set


def expand_trace(trace, logical_events):
    expanded=[]
    for item in trace:
        expanded.extend([dict(item)] * int(item.get("weight",1)))
    if not expanded:
        raise ValueError("trace is empty")
    out=[]
    while len(out)<logical_events:
        out.extend(expanded)
    return out[:logical_events]


def offsets(delay_ms):
    d=delay_ms/1000.0
    return {"node-1":0.0,"node-2":d/2.0,"node-3":d}


def simulate(trace_path, scenario_name, out_events, out_metrics, propagation_delay_ms=DEFAULT_PROPAGATION_DELAY_MS, logical_events=DEFAULT_LOGICAL_EVENTS):
    stable_policy=load_json("datasets/examples/policy_stable.json")
    candidate_policy=load_json("datasets/examples/policy_candidate_over_aggressive.json")
    required_policy=load_json("datasets/examples/policy_required.json")
    stable, candidate, required = rules(stable_policy), rules(candidate_policy), rules(required_policy)
    trace=expand_trace(load_json(trace_path), logical_events)
    node_offsets=offsets(propagation_delay_ms)
    telemetry_lag={"node-1":0,"node-2":50,"node-3":500}

    events=[]
    cumulative_events=0
    cumulative_mismatches=0
    trigger_time=None
    rollback_at={k:None for k in node_offsets}

    for logical_idx, req in enumerate(trace, start=1):
        t=(logical_idx-1)*TIME_STEP
        logical_id=f"logical-{logical_idx:05d}"
        controller_mode="shadow" if trigger_time is None else "promotion_withheld"

        for node_id, offset in node_offsets.items():
            candidate_received=t>=offset
            returned_to_stable=rollback_at[node_id] is not None and t>=rollback_at[node_id]
            candidate_active=candidate_received and not returned_to_stable
            stable_dec=allowed(stable, req)
            candidate_dec=allowed(candidate, req)
            shadow_dec=candidate_dec if candidate_active else stable_dec
            mismatch=bool(candidate_active and stable_dec != candidate_dec)
            enforced_dec=stable_dec

            cumulative_events += 1
            cumulative_mismatches += int(mismatch)
            rate=cumulative_mismatches/cumulative_events
            if trigger_time is None and cumulative_events>=MIN_EVENTS and rate>THRESHOLD:
                trigger_time=t
                for n, off in node_offsets.items():
                    rollback_at[n]=trigger_time + REACTION_DELAY_MS/1000.0 + off
                controller_mode="promotion_withheld"

            stale=bool(trigger_time is not None and candidate_active)
            events.append({
                "ts":round(t,3),"node_id":node_id,"request_id":f"{logical_id}:{node_id}",
                "logical_request_id":logical_id,"subject":req["subject"],"action":req["action"],
                "resource":req["resource"],"node_mode":"candidate-shadow" if candidate_active else "stable-shadow",
                "mode":"shadow" if candidate_active else ("rollback" if trigger_time is not None else "stable"),
                "controller_mode":controller_mode,"evaluator_version":candidate_policy["version"] if candidate_active else stable_policy["version"],
                "policy_version":candidate_policy["version"] if candidate_active else stable_policy["version"],
                "stable_decision":stable_dec,"candidate_decision":shadow_dec,"decision":shadow_dec,
                "enforced_decision":enforced_dec,"enforced":enforced_dec,
                "mismatch":mismatch,"oracle_required":allowed(required,req),"expected_rare":bool(req.get("expected_rare")),
                "withhold_triggered":trigger_time is not None,"rollback_triggered":trigger_time is not None,
                "stale_candidate_evaluator":stale,"stale_candidate":stale,
                "telemetry_ingest_lag_ms":telemetry_lag[node_id],"propagation_delay_ms":propagation_delay_ms,
            })

    with open(out_events,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(events)

    groups={}
    for e in events:
        groups.setdefault(e["logical_request_id"],set()).add(e["candidate_decision"])
    divergence=sum(len(v)>1 for v in groups.values())/max(len(groups),1)
    stale=sum(bool(e["stale_candidate_evaluator"]) for e in events)
    observed_candidate=[e for e in events if e["node_mode"]=="candidate-shadow"]
    mismatches=sum(bool(e["mismatch"]) for e in events)
    convergence_ms=None if trigger_time is None else int((max(rollback_at.values())-trigger_time)*1000)
    metrics={
        "scenario":scenario_name,"propagation_delay_ms":propagation_delay_ms,"events":len(events),
        "logical_requests":logical_events,"nodes_reported":3,"promotion_withheld":trigger_time is not None,
        "withhold_trigger_time_ms":None if trigger_time is None else int(trigger_time*1000),
        "withhold_reason":None if trigger_time is None else f"mismatch_rate_exceeded threshold={THRESHOLD}",
        "candidate_shadow_events":len(observed_candidate),"mismatches":mismatches,
        "mismatch_rate":round(mismatches/max(len(observed_candidate),1),4),
        "stale_candidate_evaluator_events":stale,"restoration_convergence_time_ms":convergence_ms,
        "policy_propagation_window_ms":propagation_delay_ms,"enforcement_divergence_rate":round(divergence,4),
        "enforced_legitimate_denials":0,
    }
    out_metrics.write_text(json.dumps({"metrics":metrics},indent=2)+"\n")
    return metrics


def generate_sensitivity(trace_path="datasets/examples/replay_trace.json"):
    rows=[]
    for delay in SENSITIVITY_DELAYS_MS:
        m=simulate(trace_path,f"delay_sensitivity_{delay}ms",RAW/f"events.delay_{delay}ms.csv",TABLES/f"distributed_metrics.delay_{delay}ms.json",delay,DEFAULT_LOGICAL_EVENTS)
        rows.append({"delay_ms":delay,"events":m["events"],"stale_exposure":m["stale_candidate_evaluator_events"],"convergence_ms":m["restoration_convergence_time_ms"],"divergence_rate":m["enforcement_divergence_rate"]})
    with open(TABLES/"delay_sensitivity.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (TABLES/"delay_sensitivity.json").write_text(json.dumps({"rows":rows},indent=2)+"\n")
    return rows


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--public-only",action="store_true")
    p.add_argument("--sensitivity-only",action="store_true")
    p.add_argument("--delay-ms",type=int,default=DEFAULT_PROPAGATION_DELAY_MS)
    p.add_argument("--logical-events",type=int,default=DEFAULT_LOGICAL_EVENTS)
    a=p.parse_args(); summary={}
    if a.sensitivity_only:
        summary["delay_sensitivity"]=generate_sensitivity()
    else:
        if not a.public_only:
            summary["synthetic"]=simulate("datasets/examples/replay_trace.json","synthetic_shadow_rollout",RAW/"events.csv",TABLES/"distributed_metrics.synthetic.json",a.delay_ms,a.logical_events)
        summary["config_derived"]=simulate("datasets/derived_graphs/public_trace.json","config_structure_derived_shadow_rollout",RAW/"public_policy_events.csv",TABLES/"distributed_metrics.public_policy.json",a.delay_ms,a.logical_events)
        summary["delay_sensitivity"]=generate_sensitivity()
    (TABLES/"simulation_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
