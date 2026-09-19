import os, time, threading, requests
from fastapi import FastAPI
from pydantic import BaseModel

NODE_ID=os.getenv("SOR_NODE_ID","node-x")
CONTROLLER=os.getenv("SOR_CONTROLLER_URL","http://localhost:8000")
TELEMETRY=os.getenv("SOR_TELEMETRY_URL","http://localhost:8100")
SYNC_INTERVAL=int(os.getenv("SOR_SYNC_INTERVAL_MS","500"))/1000
SYNC_DELAY=int(os.getenv("SOR_SYNC_DELAY_MS","0"))/1000
TELEMETRY_DELAY=int(os.getenv("SOR_TELEMETRY_DELAY_MS","0"))/1000
PARTIAL_FAILURE=os.getenv("SOR_PARTIAL_FAILURE","0")=="1"

app=FastAPI(title=f"SOR Auth Node {NODE_ID}")
state={"node_id":NODE_ID,"mode":"boot","stable_policy":{"version":"none","allow":[]},"candidate_policy":{"version":"none","allow":[]},"last_sync_at":None,"events":0,"mismatches":0}

class AuthRequest(BaseModel):
    subject:str; action:str; resource:str
    request_id:str|None=None; logical_request_id:str|None=None; expected_rare:bool=False

def allowed(policy,req):
    return any(r["subject"]==req.subject and r["action"]==req.action and r["resource"]==req.resource for r in policy.get("allow",[]))

def sync_loop():
    while True:
        try:
            if not PARTIAL_FAILURE:
                payload=requests.get(f"{CONTROLLER}/policy/latest",timeout=3).json()
                if payload["mode"]!=state["mode"] or payload["stable_policy"]["version"]!=state["stable_policy"].get("version") or payload["candidate_policy"]["version"]!=state["candidate_policy"].get("version"):
                    if SYNC_DELAY: time.sleep(SYNC_DELAY)
                    state["mode"]=payload["mode"]
                    state["stable_policy"]=payload["stable_policy"]
                    state["candidate_policy"]=payload["candidate_policy"]
                    state["last_sync_at"]=time.time()
            requests.post(f"{CONTROLLER}/nodes/report",json={"node_id":NODE_ID,"version":state["candidate_policy"].get("version","none") if state["mode"] in ["shadow","restricted"] else state["stable_policy"].get("version","none"),"mode":state["mode"],"timestamp":time.time()},timeout=3)
        except Exception:
            pass
        time.sleep(SYNC_INTERVAL)

@app.on_event("startup")
def startup(): threading.Thread(target=sync_loop,daemon=True).start()

@app.get("/health")
def health(): return {"ok":True,"state":state}

@app.post("/authorize")
def authorize(req:AuthRequest):
    stable_decision=allowed(state["stable_policy"],req)
    candidate_decision=allowed(state["candidate_policy"],req)
    mode=state["mode"]
    mismatch=bool(mode in ["shadow","restricted"] and stable_decision!=candidate_decision)
    enforced_decision=candidate_decision if mode=="restricted" else stable_decision
    state["events"]+=1; state["mismatches"]+=int(mismatch)
    event={"ts":time.time(),"node_id":NODE_ID,"request_id":req.request_id,"logical_request_id":req.logical_request_id or req.request_id,"subject":req.subject,"action":req.action,"resource":req.resource,"mode":mode,"policy_version":state["candidate_policy"].get("version") if mode in ["shadow","restricted"] else state["stable_policy"].get("version"),"stable_decision":stable_decision,"candidate_decision":candidate_decision,"decision":candidate_decision if mode in ["shadow","restricted"] else stable_decision,"enforced":enforced_decision,"mismatch":mismatch,"expected_rare":req.expected_rare}
    try:
        if TELEMETRY_DELAY: time.sleep(TELEMETRY_DELAY)
        requests.post(f"{TELEMETRY}/events",json=event,timeout=3)
    except Exception: pass
    return event
