#!/usr/bin/env python3
"""Mock cleanse vendor data."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    with (art/"vendor_inventory.csv").open(encoding="utf-8",newline="") as f:
        r=csv.DictReader(f); rows=list(r); cols=r.fieldnames or []
    ds={"columns":cols,"rows":rows}
    (art/"cleansed_dataset.json").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    (art/"cleansed_data_obj.json").write_text(json.dumps({"source":str(art/"vendor_inventory.csv"),"rows":len(rows)},indent=2)+"\n",encoding="utf-8")
    (art/"cleanse_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
