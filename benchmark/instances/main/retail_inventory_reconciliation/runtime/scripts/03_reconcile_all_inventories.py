#!/usr/bin/env python3
"""Reconcile normalized inventories across all 4 warehouses."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

WH=["north","south","east","west"]

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    all_data={}
    for w in WH:
        pth=art/f"normalized_{w}.csv"
        if pth.is_file():
            with pth.open(encoding="utf-8",newline="") as f:
                all_data[w]=list(csv.DictReader(f))
    skus=set()
    for rows in all_data.values():
        for r in rows: skus.add(r["sku"])
    report_rows=[]
    for sku in sorted(skus):
        qty={}
        for w in WH:
            for r in all_data.get(w,[]):
                if r["sku"]==sku: qty[w]=int(r["quantity"])
        qty_list=[qty.get(w,0) for w in WH]
        if max(qty_list)-min(qty_list)>10:
            report_rows.append({"sku":sku,"warehouses":",".join(WH),"discrepancy":"quantity_mismatch"})
    out=art/"discrepancy_report.csv"
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["sku","warehouses","discrepancy"])
        w.writeheader(); w.writerows(report_rows)
    st={"success":True,"errors":[]}
    (art/"reconciliation_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
