#!/usr/bin/env python3
"""Ingest DICOM metadata (JSON proxy for image headers), modality reference CSV, and quality policy."""
from __future__ import annotations
import argparse, csv, json, re
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    studies=json.loads((fd/fx["inputs"]["metadata"]).read_text(encoding="utf-8"))
    modalities={}
    with (fd/fx["inputs"]["modalities"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f):
            modalities[row["modality"]]={k:(float(v) if v else None) for k,v in row.items() if k!="modality"}
    thresholds=json.loads((fd/fx["inputs"]["thresholds"]).read_text(encoding="utf-8"))
    result={"studies":studies,"modalities":modalities,"thresholds":thresholds,"total":len(studies),"ingested_at":a.execution_time}
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"studies":len(studies),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
