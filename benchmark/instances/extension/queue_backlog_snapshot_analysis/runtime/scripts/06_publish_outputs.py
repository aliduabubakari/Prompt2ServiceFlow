#!/usr/bin/env python3
"""Publish: backlog report CSV + capacity alert + audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--execution-time",type=str,default=None); a=p.parse_args(); art=a.workspace/"artifacts"
    et=a.execution_time or "2026-07-20T09:00:00Z"; fx=json.loads(a.fixture.read_text(encoding="utf-8"))
    metrics=json.loads((art/"compute_window_metrics_artifact.json").read_text(encoding="utf-8"))
    val=json.loads((art/"validate_checkpoint_inputs_artifact.json").read_text(encoding="utf-8"))
    summary={"total":metrics["summary"]["total_windows"],"events":metrics["summary"]["total_events"],
             "rejected":val["total_rejected"],"at_risk":metrics["summary"]["windows_at_risk"]}
    manifest={"checkpoint_id":f"ckpt_queue_{et[:10].replace('-','_')}","checkpoint_time":et,
              "pipeline_id":fx["pipeline_id"],"summary":summary,"output_files":["queue_backlog_report.csv","audit_manifest.json"],"status":"completed"}
    (art/"audit_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    csv_rel="queue_backlog_report.csv"
    with (art/csv_rel).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["queue_name","window_start","event_count","max_depth","capacity_pct","capacity_at_risk","total_retries","avg_payload_kb"],extrasaction='ignore')
        w.writeheader()
        for m in metrics["per_window_metrics"]: w.writerow(m)
    (art/"publish_outputs_artifact.json").write_text(json.dumps({"manifest":manifest,"csv":csv_rel},indent=2)+"\n",encoding="utf-8")
    (art/"publish_outputs_status.json").write_text(json.dumps({"success":True,"csv":csv_rel,"summary":summary,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
