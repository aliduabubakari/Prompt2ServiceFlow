#!/usr/bin/env python3
"""Extract visual/text features: classify severity based on change magnitude and region priority."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    norm=json.loads((art/"normalize_records_artifact.json").read_text(encoding="utf-8"))
    visual=[]
    for n in norm["normalized"]:
        ch=n["change_type"]; pri=n["priority"]
        if ch=="severe_decrease" and pri in ("critical","high"): alert="critical_alert"
        elif ch in ("severe_decrease","significant_decrease"): alert="warning"
        elif ch=="significant_increase" and pri=="critical": alert="warning"
        else: alert="info"
        visual.append({"region_id":n["region_id"],"region_name":n["region_name"],"change_type":ch,
                       "ndvi_change":n["ndvi_change"],"priority":pri,"alert_level":alert,
                       "recommendation":"Immediate field investigation" if alert=="critical_alert" else ("Monitor closely" if alert=="warning" else "Routine monitoring")})
    (art/"extract_visual_text_features_artifact.json").write_text(json.dumps({"visual":visual,"total":len(visual)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_visual_text_features_status.json").write_text(json.dumps({"success":True,"extracted":len(visual),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
