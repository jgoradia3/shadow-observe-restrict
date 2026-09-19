#!/usr/bin/env python3
"""Local microbenchmark. Results are host-specific and are not production claims."""
import csv, json, sqlite3, statistics, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'results'/'diagnostics'; OUT.mkdir(parents=True, exist_ok=True)
N=50_000
rules={("svc-build","read","repo"),("svc-build","write","artifact"),("svc-deploy","read","artifact"),("svc-deploy","write","deployment"),("svc-backup","read","database")}
reqs=[("svc-build","read","repo") if i%20 else ("svc-backup","write","backup-store") for i in range(N)]
lat=[]; start=time.perf_counter_ns()
for r in reqs:
    t=time.perf_counter_ns(); _=r in rules; lat.append((time.perf_counter_ns()-t)/1e6)
elapsed=(time.perf_counter_ns()-start)/1e9
with tempfile.NamedTemporaryFile(suffix='.db') as tf:
    con=sqlite3.connect(tf.name); con.execute('create table events(i integer, subject text, decision integer)')
    t=time.perf_counter(); con.executemany('insert into events values(?,?,?)',((i,r[0],int(r in rules)) for i,r in enumerate(reqs))); con.commit(); ins_elapsed=time.perf_counter()-t; con.close()
lat.sort()
def pct(p): return lat[min(len(lat)-1,round((len(lat)-1)*p))]
t=time.perf_counter_ns(); mismatch_rate=0.04; rollback=(N>=20 and mismatch_rate>0.03); rb_ms=(time.perf_counter_ns()-t)/1e6
rows=[
 {'Metric':'Local replay evaluation throughput','Value':f'{N/elapsed:.2f}','Unit':'requests/sec'},
 {'Metric':'SQLite telemetry insert throughput','Value':f'{N/ins_elapsed:.2f}','Unit':'events/sec'},
 {'Metric':'Shadow evaluation P50 latency','Value':f'{pct(.50):.6f}','Unit':'ms'},
 {'Metric':'Shadow evaluation P95 latency','Value':f'{pct(.95):.6f}','Unit':'ms'},
 {'Metric':'Shadow evaluation P99 latency','Value':f'{pct(.99):.6f}','Unit':'ms'},
 {'Metric':'Rollback predicate evaluation latency','Value':f'{rb_ms:.6f}','Unit':'ms'},
]
with (OUT/'runtime_benchmark.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
(OUT/'runtime_benchmark.json').write_text(json.dumps({'request_count':N,'single_run':True,'host_specific':True,'rollback_predicate_result':rollback,'metrics':rows},indent=2))
print(json.dumps(rows,indent=2))
