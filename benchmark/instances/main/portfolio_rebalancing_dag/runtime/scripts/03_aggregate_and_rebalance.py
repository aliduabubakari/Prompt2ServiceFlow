#!/usr/bin/env python3
"""Aggregate all 5 portfolio analyses and calculate rebalancing trades."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    analyses=[]
    for n in ["1","2","3","4","5"]:
        pa=json.loads((art/f"portfolio_analysis_{n}.json").read_text(encoding="utf-8"))
        analyses.append(pa)
    total_value=sum(a["total_value"] for a in analyses)
    trades=[{"brokerage_id":a["brokerage_id"],"current_value":a["total_value"],"target_allocation":round(a["total_value"]/total_value,4),"rebalance_action":"BUY" if a["total_value"]/total_value<0.2 else "SELL"} for a in analyses]
    ds={"columns":["brokerage_id","current_value","target_allocation","rebalance_action"],"rows":trades}
    (art/"rebalancing_trades.json").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"errors":[]}
    (art/"rebalance_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
