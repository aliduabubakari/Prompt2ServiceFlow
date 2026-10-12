#!/usr/bin/env python3
"""Publish: enrichment report CSV + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    merged=json.loads((art/"merge_branch_outputs_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":merged["total"]+val["total_rejected"],"valid":merged["total"],"rejected":val["total_rejected"],
             "excellent":sum(1 for m in merged["merged"] if m.get("quality_grade")=="excellent"),
             "good":sum(1 for m in merged["merged"] if m.get("quality_grade")=="good"),
             "compliant":sum(1 for m in merged["merged"] if m.get("compliance_issues",99)==0)}
    manifest={"checkpoint_id":f"ckpt_product_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["product_enrichment.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="product_enrichment.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["product_id","price_tier","image_count","quality_grade","images_ok","description_ok","dimensions_ok","compliance_issues"],extrasaction='ignore')
        w.writeheader()
        for m in merged["merged"]: w.writerow(m)
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
