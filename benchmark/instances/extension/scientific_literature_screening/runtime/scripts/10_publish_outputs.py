#!/usr/bin/env python3
"""Publish: screening report CSV + review assignments + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    embedded=json.loads((art/"generate_embeddings_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":len(embedded["embedded"])+val["total_rejected"],"screened":len(embedded["embedded"]),
             "rejected":val["total_rejected"],"included":sum(1 for e in embedded["embedded"] if e["screening_decision"]=="include"),
             "excluded":sum(1 for e in embedded["embedded"] if e["screening_decision"]=="exclude")}
    manifest={"checkpoint_id":f"ckpt_lit_screen_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["screening_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="screening_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["article_id","title","journal","year","study_type","keyword_match_count","relevance_score","screening_decision","reviewer_count"],extrasaction='ignore')
        w.writeheader()
        for e in embedded["embedded"]: w.writerow(e)
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
