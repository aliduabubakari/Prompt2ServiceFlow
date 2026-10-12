#!/usr/bin/env python3
"""Score operational priority: final routing decision based on score, SLA, auto-dispatch."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    resolved=json.loads((art/"resolve_entity_conflicts_artifact.json").read_text(encoding="utf-8"))
    policy=ingested["policy"]; threshold=policy["escalation_threshold"]; scored=[]
    for r in resolved["resolved"]:
        dispatch="auto" if r.get("auto_dispatch") else ("escalate" if r["priority_score"]>=threshold else "queue")
        scored.append({**r,"dispatch_action":dispatch,"routing_decision":f"{dispatch}:{r['responsible_dept']}"})
    (art/"score_operational_priority_artifact.json").write_text(json.dumps({"scored":scored,"total":len(scored)},indent=2)+"\n",encoding="utf-8")
    (art/"score_operational_priority_status.json").write_text(json.dumps({"success":True,"scored":len(scored),
        "auto":sum(1 for s in scored if s["dispatch_action"]=="auto"),
        "escalate":sum(1 for s in scored if s["dispatch_action"]=="escalate"),
        "queue":sum(1 for s in scored if s["dispatch_action"]=="queue"),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
