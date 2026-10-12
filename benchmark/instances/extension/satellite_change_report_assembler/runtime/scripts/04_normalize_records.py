#!/usr/bin/env python3
"""Normalize: compute NDVI change, change magnitude, and classify change type."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); thresh=fx.get("change_thresholds",{})
    sig=thresh.get("ndvi_decrease_significant",0.15); sev=thresh.get("ndvi_decrease_severe",0.30)
    staged=json.loads((art/"stage_raw_artifacts_artifact.json").read_text(encoding="utf-8"))
    normalized=[]
    for s in staged["staged"]:
        diff=round(s["ndvi_after"]-s["ndvi_before"],3); abs_diff=abs(diff)
        if diff<-sev: change="severe_decrease"
        elif diff<-sig: change="significant_decrease"
        elif diff>sig: change="significant_increase"
        elif abs_diff<0.02: change="no_change"
        else: change="minor_change"
        pct=round(abs_diff/max(s["ndvi_before"],0.01)*100,1)
        normalized.append({**s,"ndvi_change":diff,"abs_ndvi_change":abs_diff,"change_type":change,"change_pct":pct})
    (art/"normalize_records_artifact.json").write_text(json.dumps({"normalized":normalized,"total":len(normalized)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_records_status.json").write_text(json.dumps({"success":True,"normalized":len(normalized),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
