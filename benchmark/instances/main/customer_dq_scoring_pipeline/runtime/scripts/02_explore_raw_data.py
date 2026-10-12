#!/usr/bin/env python3
"""Mock profile report on raw data."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"raw_customers.parquet").read_text(encoding="utf-8"))
    report={"row_count":len(ds["rows"]),"columns":ds["columns"],"null_counts":{}}
    (art/"profile_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    (art/"profile_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
