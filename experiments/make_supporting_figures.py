from pathlib import Path
import json

import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/raw/events.csv"
PUBLIC_RAW = ROOT / "results/raw/public_policy_events.csv"
TABLES = ROOT / "results/tables"
FIGS = ROOT / "results/figures"
SUMMARY = ROOT / "results" / "summary"
for p in [TABLES, FIGS, SUMMARY]:
    p.mkdir(parents=True, exist_ok=True)


def bool_col(series):
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def read_df(path):
    return pd.read_csv(path) if Path(path).exists() else pd.DataFrame()


def summarize_events(df):
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["mismatch_bool"] = bool_col(df["mismatch"])
    return df.groupby(["node_id", "mode", "policy_version"], dropna=False).agg(
        events=("request_id", "count"),
        mismatches=("mismatch_bool", "sum"),
        mismatch_rate=("mismatch_bool", "mean"),
    ).reset_index()


def low_freq(df):
    if df.empty:
        return pd.DataFrame(columns=["workflow_class", "events", "mismatch_rate", "sor_action"])
    df = df.copy()
    df["mismatch_bool"] = bool_col(df["mismatch"])
    df["expected_rare_bool"] = bool_col(df["expected_rare"])
    rows = []
    for rare_value, label in [(False, "Common workflows"), (True, "Low-frequency workflows")]:
        part = df[df["expected_rare_bool"].eq(rare_value)]
        rows.append({
            "workflow_class": label,
            "events": int(len(part)),
            "mismatch_rate": round(float(part["mismatch_bool"].mean()), 4) if len(part) else 0.0,
            "sor_action": "continue shadow evaluation" if not rare_value else "withhold promotion when aggregate threshold is exceeded",
        })
    return pd.DataFrame(rows)


def plot_figures(df):
    if df.empty:
        return
    df = df.copy()
    df["mismatch_bool"] = bool_col(df["mismatch"])
    df["ts_num"] = pd.to_numeric(df["ts"], errors="coerce")
    t0 = df["ts_num"].min()
    ts = df.assign(elapsed=df["ts_num"] - t0).sort_values("elapsed")

    rolling = ts.set_index("elapsed")["mismatch_bool"].rolling(25, min_periods=1).mean()
    plt.figure()
    rolling.plot()
    plt.xlabel("Elapsed time (s)")
    plt.ylabel("Rolling mismatch rate")
    plt.title("SOR mismatch detection during distributed rollout")
    plt.tight_layout()
    plt.savefig(FIGS / "mismatch_rate_timeseries.png", dpi=200)
    
    plt.close()

    version_counts = ts.groupby(["policy_version"]).size().reset_index(name="events")
    plt.figure()
    plt.bar(version_counts["policy_version"], version_counts["events"])
    plt.xlabel("Policy version")
    plt.ylabel("Events observed")
    plt.title("Policy-version exposure across replicas")
    plt.tight_layout()
    plt.savefig(FIGS / "policy_version_exposure.png", dpi=200)
    
    plt.close()


def load_metrics():
    # Prefer the deterministic simulator's own event-driven metrics. The generic
    # telemetry summary is retained only as a secondary diagnostic.
    p = TABLES / "distributed_metrics.synthetic.json"
    if p.exists():
        return json.loads(p.read_text()).get("metrics", {})
    p = TABLES / "distributed_metrics.json"
    if p.exists():
        return json.loads(p.read_text()).get("metrics", {})
    return {}


def read_sensitivity():
    p = TABLES / "delay_sensitivity.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["delay_ms", "events", "stale_exposure", "convergence_ms", "divergence_rate"])


def copy_summary_results():
    for src in [
        TABLES / "distributed_metrics.csv",
        TABLES / "distributed_metrics.json",
        TABLES / "node_summary.csv",
        TABLES / "low_frequency_workflows.csv",
        TABLES / "public_policy_workload_metrics.csv",
        TABLES / "delay_sensitivity.csv",
        TABLES / "delay_sensitivity.json",
    ]:
        if src.exists():
            (SUMMARY / src.name).write_bytes(src.read_bytes())


def public_metrics(df):
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["mismatch_bool"] = bool_col(df["mismatch"])
    df["expected_rare_bool"] = bool_col(df["expected_rare"])
    return pd.DataFrame([{
        "scenario": "config_structure_derived_rollout",
        "events": int(len(df)),
        "rare_workflow_events": int(df["expected_rare_bool"].sum()),
        "mismatch_rate": round(float(df["mismatch_bool"].mean()), 4),
        "rare_workflow_mismatch_rate": round(float(df.loc[df["expected_rare_bool"], "mismatch_bool"].mean()), 4),
        "policy_version_count": int(df["policy_version"].nunique()),
    }])


def main():
    df = read_df(RAW)
    public_df = read_df(PUBLIC_RAW)

    node_summary = summarize_events(df)
    node_summary.to_csv(TABLES / "node_summary.csv", index=False)

    low = low_freq(df)
    low.to_csv(TABLES / "low_frequency_workflows.csv", index=False)

    pm = public_metrics(public_df)
    pm.to_csv(TABLES / "public_policy_workload_metrics.csv", index=False)

    sensitivity = read_sensitivity()

    plot_figures(df)
    metrics = load_metrics()
    copy_summary_results()
    print("Generated supporting CSV summaries and figures")


if __name__ == "__main__":
    main()
