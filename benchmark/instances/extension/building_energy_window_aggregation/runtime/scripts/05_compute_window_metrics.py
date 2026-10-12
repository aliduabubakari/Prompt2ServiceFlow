#!/usr/bin/env python3
"""Compute window metrics: demand vs limit, energy total, power factor, at-risk flags."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_bounded_events_artifact.json").read_text(encoding="utf-8"))
    windows=json.loads((art/"build_analysis_windows_artifact.json").read_text(encoding="utf-8"))
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); dth=fx.get("demand_threshold_pct",85)
    buildings=ingested["buildings"]; metrics=[]
    for w in windows["windows"]:
        b=buildings.get(w["building_id"],{}); limit=float(b.get("demand_limit_kw",100))
        max_demand=max(e.get("demand_kw",0) for e in w["events"])
        total_energy=sum(e.get("energy_kwh",0) for e in w["events"])
        avg_pf=round(sum(e.get("power_factor",0) for e in w["events"])/max(w["event_count"],1),2)
        demand_pct=round(max_demand/limit*100,1); at_risk=demand_pct>=dth
        metrics.append({"building_id":w["building_id"],"window_index":w["window_index"],"window_start":w["window_start"],
                        "event_count":w["event_count"],"total_energy_kwh":round(total_energy,1),"max_demand_kw":max_demand,
                        "demand_limit_kw":limit,"demand_pct":demand_pct,"demand_at_risk":at_risk,"avg_power_factor":avg_pf})
    summary={"total_windows":len(metrics),"total_energy":round(sum(m["total_energy_kwh"] for m in metrics),1),
             "windows_at_risk":sum(1 for m in metrics if m["demand_at_risk"])}
    result={"per_window_metrics":metrics,"summary":summary}
    (art/"compute_window_metrics_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"compute_window_metrics_status.json").write_text(json.dumps({"success":True,"windows":len(metrics),"at_risk":summary["windows_at_risk"],"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
