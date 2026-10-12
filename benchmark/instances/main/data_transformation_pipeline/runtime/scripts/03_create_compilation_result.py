#!/usr/bin/env python3
"""Mock create compilation result."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ref={"name":"projects/whejna/locations/europe-west3/repositories/training-repo/compilationResults/cr-001"}
    (art/"compilation_result_ref.json").write_text(json.dumps(ref,indent=2)+"\n",encoding="utf-8")
    (art/"creation_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
