#!/usr/bin/env python3
"""Extract visual/text features: classify quality and assign confidence tier."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    norm=json.loads((art/"normalize_records_artifact.json").read_text(encoding="utf-8"))
    visual=[]
    for n in norm["normalized"]:
        ocr=n["ocr_confidence"]
        tier="high" if ocr>=0.85 else ("medium" if ocr>=0.65 else "low")
        visual.append({**n,"confidence_tier":tier,"needs_manual":n["issue_count"]>0 or tier=="low"})
    (art/"extract_visual_text_features_artifact.json").write_text(json.dumps({"visual":visual,"total":len(visual)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_visual_text_features_status.json").write_text(json.dumps({"success":True,"extracted":len(visual),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
