#!/usr/bin/env python3
"""Score branch quality: compute OCR, scan, and overall quality grades per claim."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    grades=ingested["thresholds"]["quality_grades"]
    scored=[]
    for c in validated["valid_claims"]:
        sq=c["scan_quality"]; ocr=c["ocr_confidence"]
        if sq>=grades["excellent"]["scan_quality_min"] and ocr>=grades["excellent"]["ocr_confidence_min"]: grade="excellent"
        elif sq>=grades["acceptable"]["scan_quality_min"] and ocr>=grades["acceptable"]["ocr_confidence_min"]: grade="acceptable"
        else: grade="poor"
        scored.append({"claim_id":c["claim_id"],"scan_quality":sq,"ocr_confidence":ocr,"quality_grade":grade})
    (art/"score_branch_quality_artifact.json").write_text(json.dumps({"scores":scored,"total":len(scored)},indent=2)+"\n",encoding="utf-8")
    (art/"score_branch_quality_status.json").write_text(json.dumps({"success":True,"scored":len(scored),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
