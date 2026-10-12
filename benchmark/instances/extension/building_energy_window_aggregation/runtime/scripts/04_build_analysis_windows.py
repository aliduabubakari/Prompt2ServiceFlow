#!/usr/bin/env python3
"""Build analysis windows: group readings by building + fixed time windows."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timedelta
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); wm=fx.get("window_size_minutes",30)
    sorted_d=json.loads((art/"sort_and_deduplicate_records_artifact.json").read_text(encoding="utf-8"))
    events=sorted_d["events"]; buildings={}
    for e in events: buildings.setdefault(e["building_id"],[]).append(e)
    windows=[]; bs=datetime.fromisoformat(fx["batch_window_start"].replace("Z","+00:00"))
    be=datetime.fromisoformat(fx["batch_window_end"].replace("Z","+00:00"))
    for bid,bev in buildings.items():
        ws=bs; wi=0
        while ws<be:
            we=ws+timedelta(minutes=wm)
            win=[e for e in bev if ws<=datetime.fromisoformat(e["timestamp"].replace("Z","+00:00"))<we]
            if win: windows.append({"building_id":bid,"window_index":wi,"window_start":ws.isoformat()+"Z","window_end":we.isoformat()+"Z","events":win,"event_count":len(win)})
            ws=we; wi+=1
    result={"windows":windows,"total_windows":len(windows)}
    (art/"build_analysis_windows_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"build_analysis_windows_status.json").write_text(json.dumps({"success":True,"windows":len(windows),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
