#!/usr/bin/env python3
"""Mock geocode facility addresses."""
from __future__ import annotations
import argparse, json
from pathlib import Path
COORDS={"City General Hospital":(40.7128,-74.0060),"Community Health Center":(37.7749,-122.4194),"Regional Medical Center":(39.7392,-104.9903)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"formatted_facilities_json.json").read_text(encoding="utf-8"))
    erows=[]
    for row in src["rows"]:
        name=row.get("facility_name",""); lat,lon=COORDS.get(name,(0,0))
        r2=dict(row); r2["latitude"]=lat; r2["longitude"]=lon; erows.append(r2)
    out={"columns":src["columns"]+["latitude","longitude"],"rows":erows,"row_count":len(erows),"geocoding":{"provider_id":"geocodingHere"}}
    (art/"geocoded_facilities_json.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"geocoder_id":"geocodingHere","rows_processed":len(erows),"rows_geocoded":len(erows),"rows_failed":0,"output_uri":str(art/"geocoded_facilities_json.json"),"errors":[]}
    (art/"geocoding_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
