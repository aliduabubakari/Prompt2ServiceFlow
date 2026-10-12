#!/usr/bin/env python3
"""Generate run ID."""
from __future__ import annotations
import argparse, json, uuid
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    rid=f"dataform-run-{uuid.uuid4()!s}"
    (art/"run_id.txt").write_text(rid+"\n",encoding="utf-8")
    (art/"gen_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
