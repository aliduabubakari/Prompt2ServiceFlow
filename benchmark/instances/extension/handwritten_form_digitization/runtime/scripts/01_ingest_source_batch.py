#!/usr/bin/env python3
"""Ingest form submissions JSON and form templates CSV."""  
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    forms=json.loads((fd/fx["inputs"]["forms"]).read_text(encoding="utf-8"))
    templates={}
    with (fd/fx["inputs"]["templates"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): templates[row["form_type"]]=row
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps({"forms":forms,"templates":templates,"total":len(forms),"ingested_at":a.execution_time},indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"forms":len(forms),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
