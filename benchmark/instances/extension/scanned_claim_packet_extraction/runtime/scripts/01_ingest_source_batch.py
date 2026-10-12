#!/usr/bin/env python3
"""Ingest scanned claim packets (JSON metadata proxy for PDF/images), policy CSV, and quality thresholds."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    claims=json.loads((fd/fx["inputs"]["claims"]).read_text(encoding="utf-8"))
    policies={}
    with (fd/fx["inputs"]["policies"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): policies[row["policy_number"]]=row
    thresholds=json.loads((fd/fx["inputs"]["thresholds"]).read_text(encoding="utf-8"))
    result={"claims":claims,"policies":policies,"thresholds":thresholds,"total_claims":len(claims),"total_policies":len(policies),"ingested_at":a.execution_time}
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"claims":len(claims),"policies":len(policies),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
