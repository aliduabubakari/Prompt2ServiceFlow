#!/usr/bin/env python3
"""Merge: combine approved and exception records into final disposition."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    app=json.loads((art/"route_approved_records_artifact.json").read_text(encoding="utf-8"))
    exc=json.loads((art/"route_exception_records_artifact.json").read_text(encoding="utf-8"))
    merged={"disposition":"complete","summary":{"total":app["total"]+exc["total"],"approved":app["total"],"exceptions":exc["total"]},
            "approved":app["records"],"exceptions":exc["records"]}
    (art/"merge_route_outcomes_artifact.json").write_text(json.dumps(merged,indent=2)+"\n",encoding="utf-8")
    (art/"merge_route_outcomes_status.json").write_text(json.dumps({"success":True,"merged":merged["summary"]["total"],"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
