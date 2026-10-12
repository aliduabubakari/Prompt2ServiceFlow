#!/usr/bin/env python3
"""Validate keyword extraction."""
from __future__ import annotations
import argparse, json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"featured.parquet").read_text(encoding="utf-8"))
    ok=all(r.get("keywords","")!="" for r in ds["rows"])
    (art/"validation_result.json").write_text(json.dumps({"valid":ok,"success":True},indent=2)+"\n",encoding="utf-8")
    (art/"validation_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
