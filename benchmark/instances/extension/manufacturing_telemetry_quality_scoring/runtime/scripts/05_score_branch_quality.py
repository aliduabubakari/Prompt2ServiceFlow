#!/usr/bin/env python3
"""Score quality: check telemetry against machine-specific thresholds."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    machines=ingested["machines"]; scores=[]
    for t in validated["valid_records"]:
        m=machines.get(t["machine_id"],{})
        issues=[]
        max_temp=float(m.get("max_temp_c",100))
        max_vib=float(m.get("max_vibration_rms",100))
        if t.get("avg_temp_c",0)>max_temp: issues.append(f"temp_high: {t['avg_temp_c']}>{max_temp}")
        if t.get("vibration_rms",0)>max_vib: issues.append(f"vibration_high: {t['vibration_rms']}>{max_vib}")
        scores.append({"machine_id":t["machine_id"],"shift":t["shift"],"temp_c":t.get("avg_temp_c"),
                        "vibration_rms":t.get("vibration_rms"),"threshold_issues":len(issues),"issues":issues})
    (art/"score_branch_quality_artifact.json").write_text(json.dumps({"scores":scores,"total":len(scores)},indent=2)+"\n",encoding="utf-8")
    (art/"score_branch_quality_status.json").write_text(json.dumps({"success":True,"scored":len(scores),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
