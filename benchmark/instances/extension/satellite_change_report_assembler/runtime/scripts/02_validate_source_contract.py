#!/usr/bin/env python3
"""Validate: required fields, region existence, date ordering, cloud cover threshold."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    images,ref,thresh=ingested["images"],ingested["reference"],ingested.get("thresholds",{})
    if not thresh:
        fx=json.loads(a.fixture.read_text(encoding="utf-8")); thresh=fx.get("change_thresholds",{})
    cloud_max=thresh.get("cloud_cover_max_pct",30); min_days=thresh.get("min_days_between",1)
    required={"region_id","before_date","after_date","ndvi_before","ndvi_after","cloud_cover_pct"}
    errors=[]; valid=[]
    for img in images:
        issues=[]
        if required-set(img.keys()): issues.append(f"missing_fields: {required-set(img.keys())}")
        if img.get("region_id") not in ref: issues.append(f"unknown_region: {img.get('region_id')}")
        if img.get("cloud_cover_pct",0)>cloud_max: issues.append(f"excessive_cloud: {img.get('cloud_cover_pct')}%>{cloud_max}%")
        try:
            b=datetime.strptime(img["before_date"],"%Y-%m-%d"); a_d=datetime.strptime(img["after_date"],"%Y-%m-%d")
            if (a_d-b).days<min_days: issues.append(f"insufficient_days: {(a_d-b).days}<{min_days}")
        except: issues.append("invalid_dates")
        if issues: errors.append({"region_id":img.get("region_id","?"),"issues":issues})
        else: valid.append(img)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
