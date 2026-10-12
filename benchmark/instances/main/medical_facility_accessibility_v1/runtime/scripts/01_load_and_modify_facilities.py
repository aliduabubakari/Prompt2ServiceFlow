#!/usr/bin/env python3
"""Load facility CSV and produce structured JSON."""
from __future__ import annotations
import argparse, csv, json, shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args()
    art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    dest=art/"facilities.csv"; shutil.copyfile(a.fixture,dest)
    with dest.open(encoding="utf-8",newline="") as f:
        r=csv.DictReader(f); rows=list(r); cols=r.fieldnames or []
    out={"columns":cols,"rows":rows,"row_count":len(rows),"dataset_id":"2","table_name":"JOT_"}
    (art/"formatted_facilities_json.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"rows_read":len(rows),"rows_written":len(rows),"output_uri":str(art/"formatted_facilities_json.json"),"errors":[]}
    (art/"format_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
