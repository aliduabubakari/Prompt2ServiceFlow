#!/usr/bin/env python3
"""Enrich branch context: match claims against policy reference data."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    policies=ingested["policies"]
    enriched=[]
    for c in validated["valid_claims"]:
        pol=policies.get(c["policy_number"],{})
        claimant_match=c.get("claimant_name")==pol.get("policyholder_name","")
        enriched.append({"claim_id":c["claim_id"],"policy_number":c["policy_number"],
                         "claimant":c["claimant_name"],"policyholder":pol.get("policyholder_name","?"),
                         "claimant_match":claimant_match,"coverage_limit":float(pol.get("coverage_limit",0)),
                         "policy_status":pol.get("status","unknown"),"deductible":float(pol.get("deductible",0))})
    (art/"enrich_branch_context_artifact.json").write_text(json.dumps({"enriched":enriched,"total":len(enriched)},indent=2)+"\n",encoding="utf-8")
    (art/"enrich_branch_context_status.json").write_text(json.dumps({"success":True,"enriched":len(enriched),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
