#!/usr/bin/env python3
"""Publish: change report CSV + alert summary + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T12:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    joined=json.loads((art/"join_reference_metadata_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    summary={"total":joined["total"]+val["total_rejected"],"valid":joined["total"],"rejected":val["total_rejected"],
             "critical_alert":sum(1 for j in joined["joined"] if j["alert_level"]=="critical_alert"),
             "warning":sum(1 for j in joined["joined"] if j["alert_level"]=="warning"),
             "info":sum(1 for j in joined["joined"] if j["alert_level"]=="info")}
    manifest={"checkpoint_id":f"ckpt_sat_change_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,
              "output_files":["satellite_change_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="satellite_change_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["region_id","region_name","region_type","protection","priority","ndvi_change","change_type","alert_level","recommendation","area_ha"])
        w.writeheader()
        for j in joined["joined"]: w.writerow({k:j.get(k,"") for k in w.fieldnames})
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv_exported":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
