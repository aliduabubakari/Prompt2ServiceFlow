#!/usr/bin/env python3
"""Extract features: compute per-shift metrics (defect rate, utilization, cycles vs rated)."""
from __future__ import annotations
import argparse, json
from pathlib import Path

SHIFT_MINUTES=480
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    machines=ingested["machines"]; features=[]
    for t in validated["valid_records"]:
        m=machines.get(t["machine_id"],{})
        rated=int(m.get("rated_cycles_per_shift",1))
        dr=round(t["defect_count"]/max(t["cycle_count"],1)*100,2)
        util=round(t["uptime_min"]/SHIFT_MINUTES*100,1)
        features.append({"machine_id":t["machine_id"],"shift":t["shift"],"date":t["date"],
                         "defect_rate_pct":dr,"utilization_pct":util,
                         "cycle_efficiency_pct":round(t["cycle_count"]/rated*100,1)})
    (art/"extract_branch_features_artifact.json").write_text(json.dumps({"features":features,"total":len(features)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_branch_features_status.json").write_text(json.dumps({"success":True,"extracted":len(features),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
