import json
from pathlib import Path

import pandas as pd
import requests


def _bool(s):
    return s.astype(str).str.lower().isin(["true", "1", "yes"])


def _safe_controller(controller_url):
    try:
        state = requests.get(f"{controller_url}/health", timeout=5).json()["state"]
        nodes = requests.get(f"{controller_url}/nodes", timeout=5).json()
        return state, nodes
    except Exception:
        return {}, {}


def _metrics_from_df(df, state=None, nodes=None, scenario="distributed_rollout"):
    state = state or {}
    nodes = nodes or {}
    metrics = {"scenario": scenario}

    if df.empty:
        metrics.update({
            "events": 0, "mismatch_rate": 0.0, "rollback_triggered": False,
            "rollback_reason": None, "nodes_reported": len(nodes), "consistent_versions": False,
            "policy_version_count": 0, "stale_candidate_events": 0,
            "rollback_mode_events": 0, "rare_workflow_events": 0,
            "rare_workflow_mismatch_rate": 0.0, "enforcement_divergence_rate": 0.0,
            "restoration_convergence_time_ms": None, "policy_propagation_window_ms": None,
            "stale_policy_exposure_events": 0,
        })
        return metrics

    mismatch = _bool(df["mismatch"]) if "mismatch" in df else pd.Series([False] * len(df))
    rare = _bool(df["expected_rare"]) if "expected_rare" in df else pd.Series([False] * len(df))

    group_key = "logical_request_id" if "logical_request_id" in df.columns else "request_id"
    if group_key in df.columns and "decision" in df.columns:
        divergence_rate = float(df.groupby(group_key)["decision"].nunique().gt(1).mean())
    else:
        divergence_rate = 0.0

    versions = list(df.get("policy_version", pd.Series(dtype=str)).dropna().astype(str).unique())
    stale_events = int(_bool(df["stale_candidate"]).sum()) if "stale_candidate" in df else 0
    rollback_mode_events = int(df.get("mode", pd.Series(dtype=str)).astype(str).eq("rollback").sum())
    node_count = int(df.get("node_id", pd.Series(dtype=str)).dropna().nunique()) or len(nodes)

    # Estimate timing windows from event observations when available.
    policy_window_ms = None
    rollback_convergence_ms = None
    if "ts" in df and "policy_version" in df:
        # Propagation window is estimated as the spread between the first observed
        # candidate-policy event at each node, not the whole duration for which
        # candidate events were observed. This keeps Docker metrics aligned with
        # the distributed rollout interpretation.
        candidate_rows = df[df["policy_version"].astype(str).str.contains("candidate", na=False)].copy()
        if not candidate_rows.empty and "node_id" in candidate_rows:
            candidate_rows["ts_num"] = pd.to_numeric(candidate_rows["ts"], errors="coerce")
            first_candidate_by_node = candidate_rows.groupby("node_id")["ts_num"].min().dropna()
            if len(first_candidate_by_node) > 1:
                policy_window_ms = int((first_candidate_by_node.max() - first_candidate_by_node.min()) * 1000)
            elif len(first_candidate_by_node) == 1:
                policy_window_ms = 0
        if "controller_mode" in df:
            rb = df[df["controller_mode"].astype(str).eq("rollback")].copy()
            stable_after_rb = rb[rb["policy_version"].astype(str).str.contains("stable", na=False)].copy()
            if not rb.empty and not stable_after_rb.empty:
                rb_start = pd.to_numeric(rb["ts"], errors="coerce").min()
                if "node_id" in stable_after_rb:
                    stable_after_rb["ts_num"] = pd.to_numeric(stable_after_rb["ts"], errors="coerce")
                    last_node_stable = stable_after_rb.groupby("node_id")["ts_num"].min().dropna().max()
                    rollback_convergence_ms = int((last_node_stable - rb_start) * 1000)
                else:
                    rollback_convergence_ms = int((pd.to_numeric(stable_after_rb["ts"], errors="coerce").max() - rb_start) * 1000)

    node_versions = [v.get("version") for v in nodes.values()] if nodes else versions
    metrics.update({
        "events": int(len(df)),
        "mismatch_rate": round(float(mismatch.mean()), 4),
        "rollback_triggered": bool(state.get("promotion_withheld_at") is not None or state.get("rollback_triggered_at") is not None or (_bool(df.get("rollback_triggered", pd.Series([False] * len(df)))).any() if "rollback_triggered" in df else False) or rollback_mode_events > 0),
        "rollback_reason": state.get("safety_reason") or state.get("rollback_reason"),
        "nodes_reported": node_count,
        "consistent_versions": bool(len(set(node_versions)) <= 1) if node_versions else False,
        "policy_version_count": int(len(set(versions))),
        "stale_candidate_events": stale_events,
        "rollback_mode_events": rollback_mode_events,
        "rare_workflow_events": int(rare.sum()),
        "rare_workflow_mismatch_rate": round(float(mismatch[rare].mean()), 4) if rare.any() else 0.0,
        "enforcement_divergence_rate": round(divergence_rate, 4),
        "restoration_convergence_time_ms": rollback_convergence_ms,
        "policy_propagation_window_ms": policy_window_ms,
        "stale_policy_exposure_events": stale_events,
    })
    return metrics


def collect_metrics(controller_url="http://localhost:8000", event_csv="results/raw/events.csv", out_dir="results/tables"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(event_csv) if Path(event_csv).exists() else pd.DataFrame()
    state, nodes = _safe_controller(controller_url)
    metrics = _metrics_from_df(df, state, nodes)

    pd.DataFrame([metrics]).to_csv(out / "distributed_metrics.csv", index=False)
    with open(out / "distributed_metrics.json", "w") as f:
        json.dump({"metrics": metrics, "controller_state": state, "nodes": nodes}, f, indent=2)
    return metrics


if __name__ == "__main__":
    print(json.dumps(collect_metrics(), indent=2))
