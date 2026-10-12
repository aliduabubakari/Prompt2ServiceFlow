#!/usr/bin/env python3
"""Mock monitor workflow completion."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    res={"status":"SUCCEEDED","state":"COMPLETED","success":True}
    (art/"invocation_status_result.json").write_text(json.dumps(res,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
