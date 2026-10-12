#!/usr/bin/env python3
"""Validate: required fields, service existence, priority validity, retry limits."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_bounded_events_artifact.json").read_text(encoding="utf-8"))
    msgs,services=ingested["messages"],ingested["services"]
    required={"message_id","queue_name","priority","enqueued_at"}; valid_p={"critical","high","medium","low"}
    errors=[]; valid=[]
    for m in msgs:
        issues=[]
        if required-set(m.keys()): issues.append(f"missing_fields: {required-set(m.keys())}")
        if m.get("queue_name") not in services: issues.append(f"unknown_queue: {m.get('queue_name')}")
        if m.get("priority") not in valid_p: issues.append(f"invalid_priority: {m.get('priority')}")
        svc=services.get(m.get("queue_name",""),{})
        max_retry=int(svc.get("max_retry_count",5))
        if m.get("retry_count",0)>max_retry: issues.append(f"retry_exceeded: {m['retry_count']}>{max_retry}")
        if issues: errors.append({"message_id":m.get("message_id","?"),"issues":issues})
        else: valid.append(m)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_checkpoint_inputs_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_checkpoint_inputs_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
