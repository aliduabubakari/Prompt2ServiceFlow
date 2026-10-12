#!/usr/bin/env python3
"""Normalize Partition B: checklist coverage — match regulatory refs to checklist items."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    checklist,policy=ingested["checklist"],ingested["policy"]; norm_b=[]
    all_regs=set(c["regulation"] for c in checklist)
    for d in validated["valid"]:
        refs=set(d.get("regulatory_refs",[]))
        covered=refs&all_regs
        total_items=sum(1 for c in checklist if c["regulation"] in refs)
        coverage=round(len(covered)/max(len(all_regs),1)*100,1)
        norm_b.append({"doc_id":d["doc_id"],"regulatory_refs":sorted(refs),"checklist_coverage_pct":coverage,
                       "total_checklist_items":total_items,"regulations_matched":len(covered)})
    (art/"normalize_partition_b_artifact.json").write_text(json.dumps({"partition":"B","records":norm_b,"total":len(norm_b)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_b_status.json").write_text(json.dumps({"success":True,"normalized":len(norm_b),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
