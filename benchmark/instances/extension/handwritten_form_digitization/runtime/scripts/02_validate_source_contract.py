#!/usr/bin/env python3
"""Validate: required fields, form type existence, OCR & scan quality minimums."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    forms,templates=ingested["forms"],ingested["templates"]; required={"form_id","form_type","ocr_confidence","scan_quality"}
    errors=[]; valid=[]
    for f in forms:
        issues=[]
        if required-set(f.keys()): issues.append(f"missing_fields: {required-set(f.keys())}")
        tmpl=templates.get(f.get("form_type",""),{})
        if not tmpl: issues.append(f"unknown_form_type: {f.get('form_type')}")
        else:
            min_ocr=float(tmpl.get("min_ocr_confidence",0.6))
            if f.get("ocr_confidence",0)<min_ocr: issues.append(f"low_ocr: {f.get('ocr_confidence')}<{min_ocr}")
            min_rec=float(tmpl.get("min_field_recognition_pct",70))
            rec_pct=f.get("fields_recognized",0)/max(f.get("field_count",1),1)*100
            if rec_pct<min_rec: issues.append(f"low_recognition: {rec_pct:.0f}%<{min_rec}%")
        if issues: errors.append({"form_id":f.get("form_id","?"),"issues":issues})
        else: valid.append(f)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_source_contract_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_source_contract_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
