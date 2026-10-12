#!/usr/bin/env python3
"""Archive regulatory reports to mock storage."""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    archive=a.workspace/"archive"; archive.mkdir(parents=True,exist_ok=True)
    reports=[]
    if (art/"fatca_report.txt").is_file():
        shutil.copy(art/"fatca_report.txt", archive/"fatca_report.txt"); reports.append("fatca")
    if (art/"irs_report.txt").is_file():
        shutil.copy(art/"irs_report.txt", archive/"irs_report.txt"); reports.append("irs")
    (archive/"archive.bin").write_bytes(b"MOCK_ARCHIVE_BINARY_CONTENT\n"*10)
    (art/"archive_input.bin").write_bytes(b"MOCK_ARCHIVE_INPUT\n"*5)
    st={"success":True,"errors":[]}
    (art/"archive_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
