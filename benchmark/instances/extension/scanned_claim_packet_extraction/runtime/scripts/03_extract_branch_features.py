#!/usr/bin/env python3
"""Extract branch features: compute claim-level features (amount category, day delta, page count)."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    today=datetime(2026,7,20)
    features=[]
    for c in validated["valid_claims"]:
        days_since=(today-datetime.strptime(c["date_of_loss"],"%Y-%m-%d")).days
        features.append({"claim_id":c["claim_id"],"amount":c["claim_amount"],"claim_type":c["claim_type"],
                         "days_since_loss":days_since,"pages":c["pages"],
                         "amount_category":"high" if c["claim_amount"]>10000 else ("medium" if c["claim_amount"]>1000 else "low")})
    (art/"extract_branch_features_artifact.json").write_text(json.dumps({"features":features,"total":len(features)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_branch_features_status.json").write_text(json.dumps({"success":True,"features_extracted":len(features),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
