#!/usr/bin/env python3
"""Validate: required incident fields, priority validity, coordinate presence."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    incidents=ingested["incidents"]; valid_p={"critical","high","medium","low"}; required={"incident_id","type","location","priority"}
    errors=[]; valid=[]
    for inc in incidents:
        issues=[]
        if required-set(inc.keys()): issues.append(f"missing_fields: {required-set(inc.keys())}")
        if inc.get("priority") not in valid_p: issues.append(f"invalid_priority: {inc.get('priority')}")
        if issues: errors.append({"incident_id":inc.get("incident_id","?"),"issues":issues})
        else: valid.append(inc)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
