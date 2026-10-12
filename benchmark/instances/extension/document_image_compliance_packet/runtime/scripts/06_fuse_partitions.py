#!/usr/bin/env python3
"""Fuse partitions: merge A+B+C into unified compliance assessment per document."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    pa=json.loads((art/"normalize_partition_a_artifact.json").read_text(encoding="utf-8"))
    pb=json.loads((art/"normalize_partition_b_artifact.json").read_text(encoding="utf-8"))
    pc=json.loads((art/"normalize_partition_c_artifact.json").read_text(encoding="utf-8"))
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    policy=ingested["policy"]; status_rules=policy["compliance_status"]
    am={r["doc_id"]:r for r in pa["records"]}; bm={r["doc_id"]:r for r in pb["records"]}; cm={r["doc_id"]:r for r in pc["records"]}
    fused=[]
    for did in am:
        doc_a,doc_b,doc_c=am[did],bm.get(did,{}),cm.get(did,{})
        coverage=doc_b.get("checklist_coverage_pct",0); sig_ok=doc_c.get("signature_compliant",False)
        qual_ok=doc_a["scan_quality"]>=policy["scan_quality_minimum"]
        if coverage>=status_rules["fully_compliant"]["min_coverage"] and (not status_rules["fully_compliant"]["require_signatures"] or sig_ok) and (not status_rules["fully_compliant"]["require_quality"] or qual_ok):
            status="fully_compliant"
        elif coverage>=status_rules["partially_compliant"]["min_coverage"]:
            status="partially_compliant"
        else: status="non_compliant"
        fused.append({"doc_id":did,"doc_type":doc_a["doc_type"],"pages":doc_a["pages"],"scan_quality":doc_a["scan_quality"],
                      "checklist_coverage_pct":coverage,"signature_compliant":sig_ok,"compliance_status":status})
    (art/"fuse_partitions_artifact.json").write_text(json.dumps({"fused":fused,"total":len(fused)},indent=2)+"\n",encoding="utf-8")
    (art/"fuse_partitions_status.json").write_text(json.dumps({"success":True,"fused":len(fused),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
