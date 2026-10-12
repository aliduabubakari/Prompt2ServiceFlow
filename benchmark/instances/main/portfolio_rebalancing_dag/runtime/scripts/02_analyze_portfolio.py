#!/usr/bin/env python3
"""Analyze portfolio metrics for a given brokerage."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--num",type=str,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ds=json.loads((art/f"holdings_dataset_{a.num}.json").read_text(encoding="utf-8"))
    total=sum(r["quantity"]*r["price"] for r in ds["rows"])
    alloc={r["symbol"]:round(r["quantity"]*r["price"]/total,4) for r in ds["rows"]}
    analysis={"total_value":round(total,2),"allocation":alloc,"risk_score":round(min(total/100000,1.0),4),"brokerage_id":f"BROKERAGE_00{a.num}"}
    (art/f"portfolio_analysis_{a.num}.json").write_text(json.dumps(analysis,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"errors":[]}
    (art/f"analysis_status_{a.num}.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
