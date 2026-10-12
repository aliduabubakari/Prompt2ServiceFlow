#!/usr/bin/env python3
"""Compute window metrics: backlog depth, capacity risk, retry pressure."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_bounded_events_artifact.json").read_text(encoding="utf-8"))
    windows=json.loads((art/"build_analysis_windows_artifact.json").read_text(encoding="utf-8"))
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); cap_thresh=fx.get("capacity_threshold_pct",80)
    services=ingested["services"]; metrics=[]
    for w in windows["windows"]:
        svc=services.get(w["queue_name"],{})
        max_depth=int(svc.get("max_queue_depth",100)); total_retries=sum(e.get("retry_count",0) for e in w["events"])
        cap_pct=round(w["event_count"]/max_depth*100,1); at_risk=cap_pct>=cap_thresh
        metrics.append({"queue_name":w["queue_name"],"window_index":w["window_index"],"window_start":w["window_start"],
                        "event_count":w["event_count"],"max_depth":max_depth,"capacity_pct":cap_pct,
                        "capacity_at_risk":at_risk,"total_retries":total_retries,
                        "avg_payload_kb":round(sum(e.get("payload_size_kb",0) for e in w["events"])/max(w["event_count"],1),1)})
    summary={"total_windows":len(metrics),"total_events":sum(m["event_count"] for m in metrics),
             "windows_at_risk":sum(1 for m in metrics if m["capacity_at_risk"])}
    result={"per_window_metrics":metrics,"summary":summary}
    (art/"compute_window_metrics_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"compute_window_metrics_status.json").write_text(json.dumps({"success":True,"windows":len(metrics),"at_risk":summary["windows_at_risk"],"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
