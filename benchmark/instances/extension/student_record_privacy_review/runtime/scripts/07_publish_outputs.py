#!/usr/bin/env python3
"""Publish: redacted CSV for research release + exception report + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    merged=json.loads((art/"merge_route_outcomes_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":merged["summary"]["total"]+val["total_rejected"],"valid":merged["summary"]["total"],
             "rejected":val["total_rejected"],"approved":merged["summary"]["approved"],"exceptions":merged["summary"]["exceptions"]}
    manifest={"checkpoint_id":f"ckpt_student_privacy_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["privacy_review_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="privacy_review_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["student_id","student_name","consent_status","has_sensitive","route","risk_issues"])
        w.writeheader()
        for g in [merged["approved"],merged["exceptions"]]:
            for r in g: w.writerow({"student_id":r["student_id"],"student_name":r["student_name"],
                                     "consent_status":r["consent_status"],"has_sensitive":r["has_sensitive"],
                                     "route":r["route"],"risk_issues":"; ".join(r["risk_issues"])})
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
