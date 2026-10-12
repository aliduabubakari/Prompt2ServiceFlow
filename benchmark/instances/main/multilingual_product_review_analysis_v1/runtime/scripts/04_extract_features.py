#!/usr/bin/env python3
"""Extract text features (word count)."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"sentiment_json.json").read_text(encoding="utf-8"))
    for r in src["rows"]:
        r["word_count"]=len(r.get("review_text","").split())
    src["columns"]=src["columns"]+["word_count"]
    (art/"features_json.json").write_text(json.dumps(src,indent=2)+"\n",encoding="utf-8")
    (art/"feature_extraction_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
