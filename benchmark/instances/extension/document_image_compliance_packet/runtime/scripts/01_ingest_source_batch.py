#!/usr/bin/env python3
"""Ingest compliance documents, checklist items, and policy rules."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    docs=json.loads((fd/fx["inputs"]["documents"]).read_text(encoding="utf-8"))
    checklist=json.loads((fd/fx["inputs"]["checklist"]).read_text(encoding="utf-8"))
    policy=json.loads((fd/fx["inputs"]["policy"]).read_text(encoding="utf-8"))
    result={"documents":docs,"checklist":checklist,"policy":policy,"total_docs":len(docs),"total_checklist":len(checklist),"ingested_at":a.execution_time}
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"documents":len(docs),"checklist_items":len(checklist),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
