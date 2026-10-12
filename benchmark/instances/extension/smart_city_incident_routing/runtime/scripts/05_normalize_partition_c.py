#!/usr/bin/env python3
"""Normalize C: policy matching — compute priority score and SLA targets."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    policy=ingested["policy"]; pweights=policy["priority_weights"]; sla=policy["response_sla_minutes"]
    norm=[]
    for inc in validated["valid"]:
        score=pweights.get(inc["priority"],0)
        norm.append({"incident_id":inc["incident_id"],"priority_score":score,"sla_minutes":sla.get(inc["priority"],480),
                     "auto_dispatch":inc["type"] in policy["auto_dispatch_types"]})
    (art/"normalize_partition_c_artifact.json").write_text(json.dumps({"partition":"C","records":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_c_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
