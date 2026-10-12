#!/usr/bin/env python3
"""Sort by timestamp, deduplicate by meter_id+timestamp."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_checkpoint_inputs_artifact.json").read_text(encoding="utf-8"))
    readings=validated["valid"]; readings.sort(key=lambda r:(r.get("timestamp",""),r.get("meter_id","")))
    seen=set(); deduped=[]; dups=[]
    for r in readings:
        key=(r.get("meter_id",""),r.get("timestamp",""))
        if key in seen: dups.append(key)
        else: seen.add(key); deduped.append(r)
    result={"events":deduped,"total_before":len(readings),"total_after":len(deduped),"duplicates_removed":len(dups)}
    (art/"sort_and_deduplicate_records_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"sort_and_deduplicate_records_status.json").write_text(json.dumps({"success":True,"deduped":len(deduped),"dups":len(dups),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
