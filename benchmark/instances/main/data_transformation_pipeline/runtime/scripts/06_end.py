#!/usr/bin/env python3
"""Cleanup temporary workspace."""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    t=a.workspace/"tmp"
    existed=t.exists()
    if existed: shutil.rmtree(t)
    st={"success":True,"targets_processed":1,"targets_deleted":1 if existed else 0,"missing_targets":[] if existed else [str(t)],"errors":[]}
    (art/"cleanup_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
