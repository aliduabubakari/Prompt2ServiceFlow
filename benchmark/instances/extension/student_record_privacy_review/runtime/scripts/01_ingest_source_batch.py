#!/usr/bin/env python3
"""Ingest student records CSV, consent forms JSON, and privacy policy."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    records=[]
    with (fd/fx["inputs"]["records"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): records.append(row)
    consent_data=json.loads((fd/fx["inputs"]["consent"]).read_text(encoding="utf-8"))
    consents={c["student_id"]:c for c in consent_data["consents"]}
    policy=json.loads((fd/fx["inputs"]["policy"]).read_text(encoding="utf-8"))
    result={"records":records,"consents":consents,"policy":policy,"total":len(records),"ingested_at":a.execution_time}
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"records":len(records),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
