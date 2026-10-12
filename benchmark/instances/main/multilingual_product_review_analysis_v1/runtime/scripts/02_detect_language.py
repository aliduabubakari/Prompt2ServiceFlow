#!/usr/bin/env python3
"""Mock language detection."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"formatted_reviews_json.json").read_text(encoding="utf-8"))
    for r in src["rows"]:
        txt=r.get("review_text","")
        if "amazing" in txt.lower() or "love" in txt.lower(): r["language"]="en"
        elif "terrible" in txt.lower() or "recommande" in txt.lower(): r["language"]="fr"
        else: r["language"]="de"
    src["columns"]=src["columns"]+["language"]
    (art/"lang_detected_json.json").write_text(json.dumps(src,indent=2)+"\n",encoding="utf-8")
    (art/"lang_detection_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
