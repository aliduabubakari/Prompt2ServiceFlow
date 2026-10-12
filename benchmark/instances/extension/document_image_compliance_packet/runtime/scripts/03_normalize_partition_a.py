#!/usr/bin/env python3
"""Normalize Partition A: document metadata — type, pages, age, quality grade."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    today=datetime(2026,7,20); norm_a=[]
    for d in validated["valid"]:
        days=(today-datetime.strptime(d["review_date"],"%Y-%m-%d")).days
        norm_a.append({"doc_id":d["doc_id"],"doc_type":d["doc_type"],"pages":d["pages"],
                       "scan_quality":d["scan_quality"],"days_since_review":days,"has_signatures":d["has_signatures"]})
    (art/"normalize_partition_a_artifact.json").write_text(json.dumps({"partition":"A","records":norm_a,"total":len(norm_a)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_a_status.json").write_text(json.dumps({"success":True,"normalized":len(norm_a),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
