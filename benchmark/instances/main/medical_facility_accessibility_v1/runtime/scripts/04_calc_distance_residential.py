#!/usr/bin/env python3
"""Mock distance calculation to residential areas."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path

def haversine(lat1,lon1,lat2,lon2):
    R=6371000; p=math.pi/180
    return 2*R*math.asin(math.sqrt(0.5-math.cos((lat2-lat1)*p)/2+math.cos(lat1*p)*math.cos(lat2*p)*(1-math.cos((lon2-lon1)*p))/2))

RES_COORDS={"Metropolis Downtown Residential":(40.713,-74.006),"Riverside Residential Zone":(37.775,-122.419),"Highland Residential Area":(39.739,-104.990)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    src=json.loads((art/"pt_distance_json.json").read_text(encoding="utf-8"))
    erows=[]
    for row in src["rows"]:
        fla,flo=row.get("latitude",0),row.get("longitude",0)
        best=min((haversine(fla,flo,rla,rlo),n) for n,(rla,rlo) in RES_COORDS.items())
        r2=dict(row); r2["distance_to_residential"]=round(best[0],1); erows.append(r2)
    out={"columns":src["columns"]+["distance_to_residential"],"rows":erows,"row_count":len(erows)}
    (art/"residential_distance_json.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"rows_processed":len(erows),"rows_extended":len(erows),"output_uri":str(art/"residential_distance_json.json"),"errors":[]}
    (art/"residential_distance_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
