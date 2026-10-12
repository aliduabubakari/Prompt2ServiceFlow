#!/usr/bin/env python3
"""Extract visual/text features: derive OCR summary and completeness flags."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    merged=json.loads((art/"merge_branch_outputs_artifact.json").read_text(encoding="utf-8"))
    ocr_min=0.70; visual=[]
    for m in merged["merged"]:
        ocr_ok=m.get("quality_ocr_confidence",0)>=ocr_min
        visual.append({"claim_id":m["claim_id"],"ocr_passed":ocr_ok,
                       "text_completeness": "complete" if ocr_ok else "incomplete",
                       "pages_digitized":m.get("pages",0)})
    (art/"extract_visual_text_features_artifact.json").write_text(json.dumps({"visual":visual,"total":len(visual)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_visual_text_features_status.json").write_text(json.dumps({"success":True,"visual_extracted":len(visual),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
