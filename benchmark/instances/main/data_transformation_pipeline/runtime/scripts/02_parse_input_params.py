#!/usr/bin/env python3
"""Mock build compilation config."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    cfg={"git_commitish":"full-version","tables":["sales","customers"],"vars":{"logical_date":"2024-01-15"}}
    (art/"compilation_config.json").write_text(json.dumps(cfg,indent=2)+"\n",encoding="utf-8")
    (art/"build_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
