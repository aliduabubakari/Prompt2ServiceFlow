#!/usr/bin/env python3
"""Export enriched JSON to CSV."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"residential_distance_json.json").read_text(encoding="utf-8"))
    out=art/"enriched_facilities.csv"
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=src["columns"]); w.writeheader(); w.writerows(src["rows"])
    st={"success":True,"rows_read":len(src["rows"]),"rows_written":len(src["rows"]),"output_uri":str(out),"errors":[]}
    (art/"export_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
