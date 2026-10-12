#!/usr/bin/env python3
"""Mock FTP sensor — immediately reports file available."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    (art/"availability_decision.json").write_text(json.dumps({"available":True},indent=2)+"\n",encoding="utf-8")
    (art/"check_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
