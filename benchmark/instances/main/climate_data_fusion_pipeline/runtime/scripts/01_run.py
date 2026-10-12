#!/usr/bin/env python3
"""Climate data fusion mock."""
from __future__ import annotations
import argparse, json
from pathlib import Path
AGENCIES=["noaa","ecmwf","jma","metoffice","bom"]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--step",type=str,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    st={"success":True,"errors":[]}
    parts=a.step.split("_",1)
    if len(parts)==2:
        agency,action=parts
        if action=="dl":
            (art/f"{agency}_data.json").write_text('{"station_id":"S1","temperature":22.5,"timestamp":"2024-01-15"}\n',encoding="utf-8")
            (art/f"{agency}_csv.csv").write_text("station_id,temperature,timestamp\nS1,22.5,2024-01-15\n",encoding="utf-8")
            (art/f"{agency}_dl_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
        elif action=="norm":
            (art/f"norm_{agency}_csv.csv").write_text("station_id,temperature,timestamp\nS1,22.5,2024-01-15\n",encoding="utf-8")
            (art/f"norm_{agency}_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
    elif a.step=="merge":
        (art/"merged_dataset.parquet").write_text('{"columns":["station_id","temperature"],"rows":[]}',encoding="utf-8")
        (art/"merge_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
