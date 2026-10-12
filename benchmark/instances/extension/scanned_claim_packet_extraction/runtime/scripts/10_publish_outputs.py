#!/usr/bin/env python3
"""Publish: CSV report + flags summary + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    assessed=json.loads((art/"assess_multimodal_quality_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total_claims":assessed["total"]+validated["total_rejected"],
             "valid":assessed["total"],"rejected":validated["total_rejected"],
             "auto_approve":sum(1 for a in assessed["assessed"] if a["final_disposition"]=="auto_approve"),
             "flagged":sum(1 for a in assessed["assessed"] if a["final_disposition"]=="flagged"),
             "manual_review":sum(1 for a in assessed["assessed"] if a["final_disposition"]=="manual_review")}
    manifest={"checkpoint_id":f"ckpt_claim_extract_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["claim_assessment.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="claim_assessment.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["claim_id","amount","claim_type","quality_grade","flags","final_disposition"])
        w.writeheader()
        for a in assessed["assessed"]: w.writerow({"claim_id":a["claim_id"],"amount":a["amount"],"claim_type":a["claim_type"],"quality_grade":a.get("quality_quality_grade","?"),"flags":a["flags"],"final_disposition":a["final_disposition"]})
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
