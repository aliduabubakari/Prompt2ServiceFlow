#!/usr/bin/env python3
"""Export enriched reviews to CSV."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"features_json.json").read_text(encoding="utf-8"))
    out=art/"enriched_reviews.csv"
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=src["columns"]); w.writeheader(); w.writerows(src["rows"])
    (art/"export_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
