#!/usr/bin/env python3
"""Validate: required fields, consent existence, GPA range, enrollment year sanity."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    records,consents,policy=ingested["records"],ingested["consents"],ingested["policy"]
    max_age=policy["max_enrollment_age_years"]; cur_year=policy["current_academic_year"]
    required={"student_id","student_name","email","grade","program","gpa","consent_status"}
    errors=[]; valid=[]
    for r in records:
        issues=[]
        if required-set(r.keys()): issues.append(f"missing_fields: {required-set(r.keys())}")
        if r.get("student_id") not in consents: issues.append("missing_consent_record")
        try:
            gpa=float(r.get("gpa",0))
            if gpa<0 or gpa>4.0: issues.append(f"invalid_gpa: {gpa}")
        except: issues.append("invalid_gpa")
        try:
            ey=int(r.get("enrollment_year",cur_year))
            if cur_year-ey>max_age: issues.append(f"stale_enrollment: {cur_year-ey}>{max_age}")
        except: pass
        if issues: errors.append({"student_id":r.get("student_id","?"),"issues":issues})
        else: valid.append(r)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
