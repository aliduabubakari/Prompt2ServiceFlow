#!/usr/bin/env python3
"""Stage: join validated forms with template metadata."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    templates=ingested["templates"]; staged=[]
    for f in validated["valid"]:
        t=templates.get(f["form_type"],{})
        staged.append({**f,"department":t.get("department","?"),"routing_queue":t.get("routing_queue","auto_process"),
                       "requires_sig":t.get("requires_signature")=="true"})
    (art/"stage_raw_artifacts_artifact.json").write_text(json.dumps({"staged":staged,"total":len(staged)},indent=2)+"\n",encoding="utf-8")
    (art/"stage_raw_artifacts_status.json").write_text(json.dumps({"success":True,"staged":len(staged),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
