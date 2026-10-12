#!/usr/bin/env python3
"""Clean documents."""
from __future__ import annotations
import argparse, json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"documents.parquet").read_text(encoding="utf-8"))
    for r in ds["rows"]: r["content"]=r["content"].lower().strip()
    (art/"cleaned.parquet").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    (art/"clean_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
