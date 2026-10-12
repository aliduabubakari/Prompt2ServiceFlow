#!/usr/bin/env python3
"""Mock merge into inventory DB."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    db=a.workspace/"mock_db"; db.mkdir(parents=True,exist_ok=True)
    (db/"inventory.json").write_text('{"status":"merged"}\n',encoding="utf-8")
    (art/"load_status.json").write_text(json.dumps({"success":True,"rows_written":2,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
