#!/usr/bin/env python3
"""Join reference metadata: flag coverage exceedances and policy status issues."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    merged=json.loads((art/"merge_branch_outputs_artifact.json").read_text(encoding="utf-8"))
    joined=[]
    for m in merged["merged"]:
        over_limit=m["amount"]>m.get("enrich_coverage_limit",0)
        policy_issue=m.get("enrich_policy_status")!="active"
        claimant_issue=not m.get("enrich_claimant_match",True)
        joined.append({**m,"coverage_exceeded":over_limit,"policy_not_active":policy_issue,
                       "claimant_mismatch":claimant_issue,"flags":sum([over_limit,policy_issue,claimant_issue])})
    (art/"join_reference_metadata_artifact.json").write_text(json.dumps({"joined":joined,"total":len(joined)},indent=2)+"\n",encoding="utf-8")
    (art/"join_reference_metadata_status.json").write_text(json.dumps({"success":True,"joined":len(joined),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
