#!/usr/bin/env python3
"""Mock sentiment analysis."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"lang_detected_json.json").read_text(encoding="utf-8"))
    for r in src["rows"]:
        txt=r.get("review_text","").lower()
        if any(w in txt for w in ["amazing","love","great","excellent","good"]): r["sentiment_score"]=0.85
        elif any(w in txt for w in ["terrible","bad","hate","awful"]): r["sentiment_score"]=0.15
        else: r["sentiment_score"]=0.60
    src["columns"]=src["columns"]+["sentiment_score"]
    (art/"sentiment_json.json").write_text(json.dumps(src,indent=2)+"\n",encoding="utf-8")
    (art/"sentiment_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
