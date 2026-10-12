#!/usr/bin/env python3
"""Ingest machine telemetry JSONL, machine master CSV, and quality thresholds."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    telemetry=[]
    with (fd/fx["inputs"]["telemetry"]).open(encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line: telemetry.append(json.loads(line))
    machines={}
    with (fd/fx["inputs"]["machines"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): machines[row["machine_id"]]=row
    thresholds=json.loads((fd/fx["inputs"]["thresholds"]).read_text(encoding="utf-8"))
    result={"telemetry":telemetry,"machines":machines,"thresholds":thresholds,"total":len(telemetry),"ingested_at":a.execution_time}
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"records":len(telemetry),"machines":len(machines),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
