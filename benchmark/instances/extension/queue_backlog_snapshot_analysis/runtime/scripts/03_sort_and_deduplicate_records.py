#!/usr/bin/env python3
"""Sort by enqueue time, deduplicate by message_id."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_checkpoint_inputs_artifact.json").read_text(encoding="utf-8"))
    msgs=validated["valid"]; msgs.sort(key=lambda m:(m.get("enqueued_at",""),m.get("message_id","")))
    seen=set(); deduped=[]; dups=[]
    for m in msgs:
        mid=m.get("message_id","")
        if mid in seen: dups.append(mid)
        else: seen.add(mid); deduped.append(m)
    result={"events":deduped,"total_before":len(msgs),"total_after":len(deduped),"duplicates_removed":len(dups)}
    (art/"sort_and_deduplicate_records_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"sort_and_deduplicate_records_status.json").write_text(json.dumps({"success":True,"deduped":len(deduped),"dups":len(dups),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
