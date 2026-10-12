#!/usr/bin/env python3
"""Ingest satellite image pairs (JSON metadata proxy), GeoJSON regions, and region reference CSV."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--execution-time",type=str,default=None)
    a=p.parse_args(); r=a.workspace; art=r/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); fd=a.fixture.parent
    images=json.loads((fd/fx["inputs"]["images"]).read_text(encoding="utf-8"))
    regions=json.loads((fd/fx["inputs"]["regions"]).read_text(encoding="utf-8"))
    ref={}
    with (fd/fx["inputs"]["reference"]).open(encoding="utf-8",newline="") as f:
        for row in csv.DictReader(f): ref[row["region_id"]]=row
    result={"images":images,"regions":regions,"reference":ref,"total_images":len(images),"total_regions":len(ref),"ingested_at":a.execution_time}
    (art/"ingest_source_batch_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"ingest_source_batch_status.json").write_text(json.dumps({"success":True,"images":len(images),"regions":len(ref),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
