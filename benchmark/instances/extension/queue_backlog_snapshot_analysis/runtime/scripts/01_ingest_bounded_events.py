#!/usr/bin/env python3
"""Ingest queue messages JSONL and service registry CSV."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    msgs=[]
    with (fd/fx["inputs"]["messages"]).open(encoding="utf-8") as f:
        for i,line in enumerate(f,1):
            line=line.strip()
            if line:
                m=json.loads(line); m["_line"]=i; msgs.append(m)
    services={}
    with (fd/fx["inputs"]["services"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): services[row["service_name"]]=row
    result={"messages":msgs,"services":services,"total":len(msgs),"ingested_at":a.execution_time}
    (art/"ingest_bounded_events_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_bounded_events_status.json").write_text(json.dumps({"success":True,"messages":len(msgs),"services":len(services),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
