#!/usr/bin/env python3
"""Normalize SKU formats for a warehouse."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--warehouse",type=str,required=True)
    a=p.parse_args()
    art=a.workspace/"artifacts"
    src_path=art/f"{a.warehouse}_inventory.csv"
    with src_path.open(encoding="utf-8",newline="") as f:
        r=csv.DictReader(f); rows=list(r); cols=r.fieldnames or []
    for row in rows:
        row["sku"]=row["sku"].upper().replace("-","_")
    out=art/f"normalized_{a.warehouse}.csv"
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    st={"success":True,"errors":[]}
    (art/f"{a.warehouse}_normalization_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
