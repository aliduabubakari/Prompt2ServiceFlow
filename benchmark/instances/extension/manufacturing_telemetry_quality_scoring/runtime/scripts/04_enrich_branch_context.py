#!/usr/bin/env python3
"""Enrich context: join with machine master data (type, line, age)."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    machines=ingested["machines"]; current_year=2026; enriched=[]
    for t in validated["valid_records"]:
        m=machines.get(t["machine_id"],{})
        age=current_year-int(m.get("install_year",current_year))
        enriched.append({"machine_id":t["machine_id"],"shift":t["shift"],
                         "machine_type":m.get("machine_type","?"),"production_line":m.get("production_line","?"),"machine_age_years":age})
    (art/"enrich_branch_context_artifact.json").write_text(json.dumps({"enriched":enriched,"total":len(enriched)},indent=2)+"\n",encoding="utf-8")
    (art/"enrich_branch_context_status.json").write_text(json.dumps({"success":True,"enriched":len(enriched),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
