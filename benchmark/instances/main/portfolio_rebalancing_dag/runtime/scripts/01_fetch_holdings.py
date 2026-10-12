#!/usr/bin/env python3
"""Fetch mock brokerage holdings for a given brokerage_id."""
from __future__ import annotations
import argparse, json
from pathlib import Path

HOLDINGS = {
    "BROKERAGE_001": [{"symbol":"AAPL","quantity":100,"price":198.50},{"symbol":"GOOGL","quantity":50,"price":175.20}],
    "BROKERAGE_002": [{"symbol":"MSFT","quantity":80,"price":420.10},{"symbol":"AMZN","quantity":30,"price":185.75}],
    "BROKERAGE_003": [{"symbol":"TSLA","quantity":60,"price":245.30},{"symbol":"NVDA","quantity":40,"price":950.00}],
    "BROKERAGE_004": [{"symbol":"META","quantity":70,"price":510.25},{"symbol":"NFLX","quantity":45,"price":625.80}],
    "BROKERAGE_005": [{"symbol":"JPM","quantity":120,"price":200.10},{"symbol":"V","quantity":90,"price":280.45}],
}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--brokerage",type=str,required=True); p.add_argument("--num",type=str,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    rows=HOLDINGS.get(a.brokerage,[])
    ds={"columns":["symbol","quantity","price"],"rows":rows}
    (art/f"holdings_dataset_{a.num}.json").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"errors":[]}
    (art/f"extraction_status_{a.num}.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
