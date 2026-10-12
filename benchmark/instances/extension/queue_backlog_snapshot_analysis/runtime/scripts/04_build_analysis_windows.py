#!/usr/bin/env python3
"""Build analysis windows: group messages by queue + fixed time windows."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timedelta
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); wm=fx.get("window_size_minutes",10)
    sorted_d=json.loads((art/"sort_and_deduplicate_records_artifact.json").read_text(encoding="utf-8"))
    events=sorted_d["events"]
    queues={}
    for e in events: queues.setdefault(e["queue_name"],[]).append(e)
    windows=[]
    batch_start=datetime.fromisoformat(fx["batch_window_start"].replace("Z","+00:00"))
    batch_end=datetime.fromisoformat(fx["batch_window_end"].replace("Z","+00:00"))
    for qname,qevents in queues.items():
        ws=batch_start; wi=0
        while ws<batch_end:
            we=ws+timedelta(minutes=wm)
            win_events=[e for e in qevents if ws<=datetime.fromisoformat(e["enqueued_at"].replace("Z","+00:00"))<we]
            if win_events:
                windows.append({"queue_name":qname,"window_index":wi,"window_start":ws.isoformat()+"Z","window_end":we.isoformat()+"Z","events":win_events,"event_count":len(win_events)})
            ws=we; wi+=1
    result={"windows":windows,"total_windows":len(windows)}
    (art/"build_analysis_windows_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"build_analysis_windows_status.json").write_text(json.dumps({"success":True,"windows":len(windows),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
