#!/usr/bin/env python3
"""Route exception records: escalate to data steward for manual review."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    evaluated=json.loads((art/"evaluate_policy_or_risk_artifact.json").read_text(encoding="utf-8"))
    exceptions=evaluated["exceptions"]
    result={"route":"exception","records":exceptions,"total":len(exceptions),"action":"escalate_to_steward"}
    (art/"route_exception_records_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"route_exception_records_status.json").write_text(json.dumps({"success":True,"escalated":len(exceptions),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
