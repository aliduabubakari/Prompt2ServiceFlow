#!/usr/bin/env python3
"""Mock feature engineering."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"cleaned_customers.parquet").read_text(encoding="utf-8"))
    for r in ds["rows"]:
        age=r.get("age",0)
        r["age_group"]="young" if age<30 else ("middle" if age<50 else "senior")
    ds["columns"]=ds["columns"]+["age_group"]
    (art/"final_customers.parquet").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    (art/"feature_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
