#!/usr/bin/env python3
"""Publish: compliance packet CSV + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    fused=json.loads((art/"fuse_partitions_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":fused["total"]+val["total_rejected"],"valid":fused["total"],"rejected":val["total_rejected"],
             "fully_compliant":sum(1 for f in fused["fused"] if f["compliance_status"]=="fully_compliant"),
             "partially_compliant":sum(1 for f in fused["fused"] if f["compliance_status"]=="partially_compliant"),
             "non_compliant":sum(1 for f in fused["fused"] if f["compliance_status"]=="non_compliant")}
    manifest={"checkpoint_id":f"ckpt_compliance_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["compliance_packet.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="compliance_packet.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["doc_id","doc_type","pages","scan_quality","checklist_coverage_pct","signature_compliant","compliance_status"])
        w.writeheader()
        for r in fused["fused"]: w.writerow(r)
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
