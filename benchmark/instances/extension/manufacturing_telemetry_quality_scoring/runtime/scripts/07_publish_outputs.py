#!/usr/bin/env python3
"""Publish: compute final quality grade, export CSV, write manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

SHIFT_MINUTES=480
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    merged=json.loads((art/"merge_branch_outputs_artifact.json").read_text(encoding="utf-8"))
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    grades=ingested["thresholds"]["quality_grades"]; uptime_min=ingested["thresholds"]["uptime_pct_min"]
    assessed=[]
    for m in merged["merged"]:
        issues=0
        if m.get("defect_rate_pct",0)>ingested["thresholds"]["defect_rate_max"]: issues+=1
        if m.get("utilization_pct",100)<uptime_min: issues+=1
        issues+=m.get("threshold_issues",0)
        if issues<=grades["excellent"]["max_issues"]: grade="excellent"
        elif issues<=grades["acceptable"]["max_issues"]: grade="acceptable"
        elif issues<=grades["attention"]["max_issues"]: grade="attention"
        else: grade="critical"
        assessed.append({**m,"quality_grade":grade,"total_issues":issues})
    summary={"total":len(assessed),
             "excellent":sum(1 for a in assessed if a["quality_grade"]=="excellent"),
             "acceptable":sum(1 for a in assessed if a["quality_grade"]=="acceptable"),
             "attention":sum(1 for a in assessed if a["quality_grade"]=="attention"),
             "critical":sum(1 for a in assessed if a["quality_grade"]=="critical")}
    manifest={"checkpoint_id":f"ckpt_mfg_quality_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["mfg_quality_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="mfg_quality_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        fields=["machine_id","shift","machine_type","production_line","defect_rate_pct","utilization_pct","cycle_efficiency_pct","quality_grade","total_issues"]
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for a in assessed: w.writerow({f:a.get(f,"") for f in fields})
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
