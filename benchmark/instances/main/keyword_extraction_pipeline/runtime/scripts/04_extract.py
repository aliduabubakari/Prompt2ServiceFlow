#!/usr/bin/env python3
"""Extract keywords."""
from __future__ import annotations
import argparse, json
from pathlib import Path
KW=["machine","learning","nlp","keywords","extraction","data","process"]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"cleaned.parquet").read_text(encoding="utf-8"))
    for r in ds["rows"]:
        words=r["content"].split()
        r["keywords"]=",".join(w for w in words if w.strip(",.") in KW)
    ds["columns"]=ds["columns"]+["keywords"]
    (art/"featured.parquet").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    (art/"feature_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
