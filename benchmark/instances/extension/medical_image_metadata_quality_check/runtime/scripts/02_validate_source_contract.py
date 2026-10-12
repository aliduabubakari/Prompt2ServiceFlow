#!/usr/bin/env python3
"""Validate: required DICOM fields, patient ID format, modality existence, image count minimum."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    studies,modalities,thresholds=ingested["studies"],ingested["modalities"],ingested["thresholds"]
    required=set(thresholds["required_fields"]); pid_re=re.compile(thresholds["patient_id_pattern"])
    errors=[]; valid=[]
    for s in studies:
        issues=[]
        if required-set(s.keys()): issues.append(f"missing_fields: {required-set(s.keys())}")
        if not pid_re.match(s.get("patient_id","")): issues.append(f"invalid_patient_id: {s.get('patient_id')}")
        mod=s.get("modality","")
        if mod not in modalities: issues.append(f"unknown_modality: {mod}")
        else:
            ref=modalities[mod]; min_img=ref.get("min_images",0)
            if s.get("image_count",0)<min_img: issues.append(f"insufficient_images: {s.get('image_count')}<{min_img}")
        if issues: errors.append({"study_uid":s.get("study_uid","?"),"issues":issues})
        else: valid.append(s)
    result={"valid_studies":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
