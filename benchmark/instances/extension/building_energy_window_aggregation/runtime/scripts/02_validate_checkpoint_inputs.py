#!/usr/bin/env python3
"""Validate: required fields, building existence, power factor range."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_bounded_events_artifact.json").read_text(encoding="utf-8"))
    readings,buildings=ingested["readings"],ingested["buildings"]
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); pf_min=fx.get("power_factor_min",0.85)
    required={"meter_id","building_id","timestamp","energy_kwh","demand_kw"}; errors=[]; valid=[]
    for r in readings:
        issues=[]
        if required-set(r.keys()): issues.append(f"missing_fields: {required-set(r.keys())}")
        if r.get("building_id") not in buildings: issues.append(f"unknown_building: {r.get('building_id')}")
        if r.get("power_factor",1.0)<pf_min: issues.append(f"low_power_factor: {r.get('power_factor')}<{pf_min}")
        if issues: errors.append({"meter_id":r.get("meter_id","?"),"issues":issues})
        else: valid.append(r)
    result={"valid":valid,"errors":errors,"total_valid":len(valid),"total_rejected":len(errors)}
    (art/"validate_checkpoint_inputs_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"validate_checkpoint_inputs_status.json").write_text(json.dumps({"success":True,"valid":len(valid),"rejected":len(errors),"errors":errors},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
