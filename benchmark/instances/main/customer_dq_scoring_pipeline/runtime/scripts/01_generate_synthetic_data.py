#!/usr/bin/env python3
"""Generate mock synthetic customer parquet data (as JSON for simplicity)."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    rows=[{"customer_id":f"C{i:03d}","name":f"Customer {i}","age":20+(i*7)%60,"email":f"cust{i}@example.com","purchases":i*3} for i in range(1,11)]
    ds={"columns":["customer_id","name","age","email","purchases"],"rows":rows}
    (art/"raw_customers.parquet").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    (art/"generation_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
