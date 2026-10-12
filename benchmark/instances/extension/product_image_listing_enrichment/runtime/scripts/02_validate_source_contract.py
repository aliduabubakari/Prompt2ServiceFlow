#!/usr/bin/env python3
"""Validate: required fields, category existence, image quality minimum."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    products,rules=ingested["products"],ingested["rules"]; required={"product_id","title","category","image_quality_score"}
    errors=[]; valid=[]
    for prd in products:
        issues=[]
        if required-set(prd.keys()): issues.append(f"missing_fields: {required-set(prd.keys())}")
        if prd.get("category") not in rules: issues.append(f"unknown_category: {prd.get('category')}")
        rule=rules.get(prd.get("category",""),{})
        if prd.get("image_quality_score",0)<float(rule.get("quality_threshold",0.5)): issues.append(f"low_quality: {prd.get('image_quality_score')}<{rule.get('quality_threshold')}")
        if issues: errors.append({"product_id":prd.get("product_id","?"),"issues":issues})
        else: valid.append(prd)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
