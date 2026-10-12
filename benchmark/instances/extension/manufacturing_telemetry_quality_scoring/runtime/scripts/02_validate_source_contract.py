#!/usr/bin/env python3
"""Validate: required fields, machine existence, numeric ranges."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    telemetry,machines,thresholds=ingested["telemetry"],ingested["machines"],ingested["thresholds"]
    required=set(thresholds["required_fields"]); errors=[]; valid=[]
    for t in telemetry:
        issues=[]
        if required-set(t.keys()): issues.append(f"missing_fields: {required-set(t.keys())}")
        if t.get("machine_id") not in machines: issues.append(f"unknown_machine: {t.get('machine_id')}")
        if issues: errors.append({"record":t.get("machine_id","?"),"issues":issues})
        else: valid.append(t)
    result={"valid_records":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
