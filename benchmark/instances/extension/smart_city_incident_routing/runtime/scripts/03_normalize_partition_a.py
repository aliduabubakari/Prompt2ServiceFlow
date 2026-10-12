#!/usr/bin/env python3
"""Normalize A: incident metadata — type, priority, source, age."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    now=datetime(2026,7,20,12,0,0)
    norm=[]
    for inc in validated["valid"]:
        age_h=(now-datetime.fromisoformat(inc["reported_at"].replace("Z","+00:00")).replace(tzinfo=None)).total_seconds()/3600
        norm.append({"incident_id":inc["incident_id"],"type":inc["type"],"priority":inc["priority"],
                     "source":inc.get("reported_by","?"),"age_hours":round(age_h,1)})
    (art/"normalize_partition_a_artifact.json").write_text(json.dumps({"partition":"A","records":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_a_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
