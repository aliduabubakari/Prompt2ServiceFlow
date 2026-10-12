#!/usr/bin/env python3
"""Stage: join validated image pairs with region GeoJSON properties."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    geojson=ingested["regions"]; ref=ingested["reference"]
    region_geom={f["properties"]["region_id"]:f for f in geojson["features"]}
    staged=[]
    for img in validated["valid"]:
        rid=img["region_id"]; r=ref.get(rid,{}); g=region_geom.get(rid,{})
        staged.append({**img,"region_name":r.get("region_name","?"),"region_type":r.get("region_type","?"),
                       "area_ha":float(r.get("area_ha",0)),"protection":r.get("protection_status","?"),
                       "priority":r.get("monitoring_priority","?"),"geometry_type":g.get("geometry",{}).get("type","?")})
    (art/"stage_raw_artifacts_artifact.json").write_text(json.dumps({"staged":staged,"total":len(staged)},indent=2)+"\n",encoding="utf-8")
    (art/"stage_raw_artifacts_status.json").write_text(json.dumps({"success":True,"staged":len(staged),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
