#!/usr/bin/env python3
"""Determine routing based on account type."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"transaction_dataset.json").read_text(encoding="utf-8"))
    types={r.get("account_type","") for r in ds["rows"]}
    is_international="international" in types
    route="fatca" if is_international else "irs"
    dec={"route":route,"matched":True,"reason":f"account_types found: {sorted(types)}"}
    (art/"routing_decision.json").write_text(json.dumps(dec,indent=2)+"\n",encoding="utf-8")
    (art/"route.txt").write_text(route,encoding="utf-8")
if __name__=="__main__": main()
