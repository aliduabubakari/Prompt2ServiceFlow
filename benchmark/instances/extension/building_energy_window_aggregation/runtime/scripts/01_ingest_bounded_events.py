#!/usr/bin/env python3
"""Ingest energy meter readings JSONL and building registry CSV."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    readings=[]
    with (fd/fx["inputs"]["readings"]).open(encoding="utf-8") as f:
        for i,line in enumerate(f,1):
            line=line.strip()
            if line: m=json.loads(line); m["_line"]=i; readings.append(m)
    buildings={}
    with (fd/fx["inputs"]["buildings"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): buildings[row["building_id"]]=row
    result={"readings":readings,"buildings":buildings,"total":len(readings),"ingested_at":a.execution_time}
    (art/"ingest_bounded_events_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_bounded_events_status.json").write_text(json.dumps({"success":True,"readings":len(readings),"buildings":len(buildings),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
