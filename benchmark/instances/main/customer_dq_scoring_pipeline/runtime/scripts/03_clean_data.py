#!/usr/bin/env python3
"""Mock clean customer data."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"raw_customers.parquet").read_text(encoding="utf-8"))
    cleaned=[r for r in ds["rows"] if r["customer_id"]]
    out={"columns":ds["columns"],"rows":cleaned}
    (art/"cleaned_customers.parquet").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    (art/"cleaning_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
