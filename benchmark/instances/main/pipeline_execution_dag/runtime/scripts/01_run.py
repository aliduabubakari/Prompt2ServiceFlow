#!/usr/bin/env python3
"""Pipeline execution DAG mock."""
from __future__ import annotations
import argparse, csv, json, shutil
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--step",type=str,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    st={"success":True,"errors":[]}
    if a.step=="load":
        fixture=Path(a.workspace)/"../fixtures/data.csv"
        dest=art/"data.csv"; shutil.copyfile(fixture,dest) if fixture.is_file() else dest.write_text("id\n1\n2\n3\n",encoding="utf-8")
        with dest.open(encoding="utf-8",newline="") as f: r=csv.DictReader(f); rows=list(r); cols=r.fieldnames or []
        (art/"formatted_json.json").write_text(json.dumps({"columns":cols,"rows":rows},indent=2)+"\n",encoding="utf-8")
        (art/"format_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
    elif a.step=="reconcile":
        (art/"reconciled_json.json").write_text(json.dumps({"columns":["id","name"],"rows":[{"id":1,"name":"A"}]},indent=2)+"\n",encoding="utf-8")
        (art/"reconciliation_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
    elif a.step=="weather":
        (art/"weather_json.json").write_text(json.dumps({"columns":["id","temp"],"rows":[]},indent=2)+"\n",encoding="utf-8")
        (art/"weather_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
    elif a.step=="extend":
        (art/"extended_json.json").write_text(json.dumps({"columns":["id","risk"],"rows":[]},indent=2)+"\n",encoding="utf-8")
        (art/"extension_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
    elif a.step=="save":
        (art/"output.csv").write_text("id,risk\n",encoding="utf-8")
        (art/"export_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
