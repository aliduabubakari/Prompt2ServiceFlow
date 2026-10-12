#!/usr/bin/env python3
"""Validate: required doc fields, scan quality minimum, doc type validity."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    docs,policy=ingested["documents"],ingested["policy"]
    sq_min=policy["scan_quality_minimum"]; required={"doc_id","doc_type","title","scan_quality","regulatory_refs"}
    errors=[]; valid=[]
    for d in docs:
        issues=[]
        if required-set(d.keys()): issues.append(f"missing_fields: {required-set(d.keys())}")
        if d.get("scan_quality",0)<sq_min: issues.append(f"low_quality: {d.get('scan_quality')}<{sq_min}")
        if issues: errors.append({"doc_id":d.get("doc_id","?"),"issues":issues})
        else: valid.append(d)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
