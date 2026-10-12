#!/usr/bin/env python3
"""Normalize B: asset proximity — match incidents to nearest registered assets."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    assets=ingested["assets"]
    # Simple location-based matching (substring)
    norm=[]
    for inc in validated["valid"]:
        matched=[aid for aid,ast in assets.items() if any(w in inc.get("location","") for w in ast.get("location","").replace("&","").split())]
        norm.append({"incident_id":inc["incident_id"],"nearby_assets":matched,"asset_count":len(matched)})
    (art/"normalize_partition_b_artifact.json").write_text(json.dumps({"partition":"B","records":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_b_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
