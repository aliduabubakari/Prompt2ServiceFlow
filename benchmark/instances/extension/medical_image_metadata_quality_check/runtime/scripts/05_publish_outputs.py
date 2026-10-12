#!/usr/bin/env python3
"""Publish: CSV quality report + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    norm=json.loads((art/"normalize_records_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":norm["total"]+val["total_rejected"],"valid":norm["total"],"rejected":val["total_rejected"],
             "pass":sum(1 for n in norm["normalized"] if n["quality_grade"]=="pass"),
             "warning":sum(1 for n in norm["normalized"] if n["quality_grade"]=="warning"),
             "fail":sum(1 for n in norm["normalized"] if n["quality_grade"]=="fail")}
    manifest={"checkpoint_id":f"ckpt_dicom_qc_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["dicom_quality_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="dicom_quality_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["study_uid","patient_id","modality","body_part","image_count","quality_grade","issue_count","issues"])
        w.writeheader()
        for n in norm["normalized"]: w.writerow({**n,"issues":"; ".join(n["issues"])})
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
