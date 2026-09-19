import csv, os, time, threading, requests
from pathlib import Path
from fastapi import FastAPI

CONTROLLER = os.getenv("SOR_CONTROLLER_URL", "http://localhost:8000")
RESULTS = Path(os.getenv("SOR_RESULTS_DIR", "results/raw"))
RESULTS.mkdir(parents=True, exist_ok=True)
EVENT_FILE = RESULTS / "events.csv"

app = FastAPI(title="SOR Telemetry Collector")
events = []
last_aggregate_idx = 0

FIELDS = ["ts","node_id","request_id","logical_request_id","subject","action","resource","mode","controller_mode","policy_version","controller_policy_version","stable_decision","candidate_decision","decision","enforced","mismatch","expected_rare","rollback_triggered","stale_candidate","telemetry_ingest_lag_ms"]
if not EVENT_FILE.exists():
    with open(EVENT_FILE, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writeheader()

def aggregate_loop():
    global last_aggregate_idx
    while True:
        time.sleep(1)
        batch = events[last_aggregate_idx:]
        if batch:
            mismatches = sum(1 for e in batch if e.get("mismatch"))
            try:
                requests.post(f"{CONTROLLER}/telemetry/aggregate", json={"events": len(batch), "mismatches": mismatches}, timeout=3)
                last_aggregate_idx += len(batch)
            except Exception:
                pass

@app.on_event("startup")
def startup():
    threading.Thread(target=aggregate_loop, daemon=True).start()

@app.get("/health")
def health():
    return {"ok": True, "events": len(events)}

@app.post("/events")
def ingest(event: dict):
    events.append(event)
    # Older node events may not contain controller-derived fields; leave them blank rather than failing.
    row = {k: event.get(k) for k in FIELDS}
    with open(EVENT_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
    return {"ok": True}

@app.get("/events")
def list_events():
    return events
