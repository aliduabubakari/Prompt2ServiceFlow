#!/usr/bin/env python3
"""Join reference metadata: flag protection status and area concerns."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    visual=json.loads((art/"extract_visual_text_features_artifact.json").read_text(encoding="utf-8"))
    norm=json.loads((art/"normalize_records_artifact.json").read_text(encoding="utf-8"))
    nmap={n["region_id"]:n for n in norm["normalized"]}
    joined=[]
    for v in visual["visual"]:
        n=nmap.get(v["region_id"],{})
        joined.append({**v,"area_ha":n.get("area_ha",0),"protection":n.get("protection","?"),
                       "region_type":n.get("region_type","?"),"cloud_cover_pct":n.get("cloud_cover_pct",0),
                       "resolution_m":n.get("resolution_m",10)})
    (art/"join_reference_metadata_artifact.json").write_text(json.dumps({"joined":joined,"total":len(joined)},indent=2)+"\n",encoding="utf-8")
    (art/"join_reference_metadata_status.json").write_text(json.dumps({"success":True,"joined":len(joined),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
