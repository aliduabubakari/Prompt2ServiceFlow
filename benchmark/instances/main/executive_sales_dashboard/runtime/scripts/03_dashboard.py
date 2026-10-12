#!/usr/bin/env python3
"""Mock generate dashboard."""
from __future__ import annotations
import argparse, json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    (art/"dashboard.html").write_text("<html><h1>Sales Dashboard</h1><p>Executive Summary</p></html>",encoding="utf-8")
    (art/"render_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
