#!/usr/bin/env python3
"""Mock load sales CSV."""
from __future__ import annotations
import argparse, csv, json, shutil
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    dest=art/"sales.csv"; shutil.copyfile(a.fixture,dest)
    with dest.open(encoding="utf-8",newline="") as f:
        r=csv.DictReader(f); rows=list(r); cols=r.fieldnames or []
    ds={"columns":cols,"rows":rows}
    (art/"validated_dataset.json").write_text(json.dumps(ds,indent=2)+"\n",encoding="utf-8")
    (art/"validated_data.json").write_text(json.dumps({"rows":len(rows),"success":True},indent=2)+"\n",encoding="utf-8")
    (art/"validation_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
