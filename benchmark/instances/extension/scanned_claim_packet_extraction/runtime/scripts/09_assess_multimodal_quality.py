#!/usr/bin/env python3
"""Assess multimodal quality: final quality grade combining all signals."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    joined=json.loads((art/"join_reference_metadata_artifact.json").read_text(encoding="utf-8"))
    visual=json.loads((art/"extract_visual_text_features_artifact.json").read_text(encoding="utf-8"))
    vmap={v["claim_id"]:v for v in visual["visual"]}
    assessed=[]
    for j in joined["joined"]:
        v=vmap.get(j["claim_id"],{})
        # Final disposition
        if j["flags"]>=2 or j["quality_quality_grade"]=="poor" or not v.get("ocr_passed",True):
            disposition="manual_review"
        elif j["flags"]==1 or j["quality_quality_grade"]=="acceptable":
            disposition="flagged"
        else:
            disposition="auto_approve"
        assessed.append({**j,"ocr_passed":v.get("ocr_passed",False),"text_completeness":v.get("text_completeness","?"),"final_disposition":disposition})
    (art/"assess_multimodal_quality_artifact.json").write_text(json.dumps({"assessed":assessed,"total":len(assessed)},indent=2)+"\n",encoding="utf-8")
    (art/"assess_multimodal_quality_status.json").write_text(json.dumps({"success":True,"assessed":len(assessed),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
