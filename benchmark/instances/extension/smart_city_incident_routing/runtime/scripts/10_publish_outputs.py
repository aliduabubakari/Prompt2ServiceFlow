#!/usr/bin/env python3
"""Publish: routing dispatch CSV + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    scored=json.loads((art/"score_operational_priority_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":scored["total"]+val["total_rejected"],"valid":scored["total"],"rejected":val["total_rejected"],
             "auto_dispatched":sum(1 for s in scored["scored"] if s["dispatch_action"]=="auto"),
             "escalated":sum(1 for s in scored["scored"] if s["dispatch_action"]=="escalate"),
             "queued":sum(1 for s in scored["scored"] if s["dispatch_action"]=="queue")}
    manifest={"checkpoint_id":f"ckpt_city_incident_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["dispatch_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="dispatch_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["incident_id","type","priority","source","age_hours","priority_score","responsible_dept","dispatch_action","routing_decision"],extrasaction='ignore')
        w.writeheader()
        for s in scored["scored"]: w.writerow(s)
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
