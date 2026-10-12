#!/usr/bin/env python3
"""Export keyword report to CSV."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"featured.parquet").read_text(encoding="utf-8"))
    out=art/"keyword_report.csv"
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=ds["columns"]); w.writeheader(); w.writerows(ds["rows"])
    (art/"report_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
