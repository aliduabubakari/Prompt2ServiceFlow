#!/usr/bin/env python3
"""Validate: required fields, policy existence, signature presence, scan quality minimum."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    claims,policies,thresholds=ingested["claims"],ingested["policies"],ingested["thresholds"]
    required=set(thresholds["required_fields"]); sq_min=thresholds["scan_quality_minimum"]
    errors=[]; valid=[]
    for c in claims:
        issues=[]
        if required-set(c.keys()): issues.append(f"missing_fields: {required-set(c.keys())}")
        if c.get("policy_number") not in policies: issues.append(f"unknown_policy: {c.get('policy_number')}")
        if c.get("scan_quality",0)<sq_min: issues.append(f"low_scan_quality: {c.get('scan_quality')}<{sq_min}")
        if thresholds.get("signature_required") and not c.get("has_signature"): issues.append("missing_signature")
        if issues: errors.append({"claim_id":c.get("claim_id","?"),"issues":issues})
        else: valid.append(c)
    result={"valid_claims":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
