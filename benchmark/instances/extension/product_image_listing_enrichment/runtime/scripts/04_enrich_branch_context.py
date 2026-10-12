#!/usr/bin/env python3
"""Enrich branch context: match category rules, check compliance per listing."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    rules=ingested["rules"]; enriched=[]
    for prd in validated["valid"]:
        r=rules.get(prd["category"],{})
        img_ok=prd["image_count"]>=int(r.get("min_images",1))
        desc_ok=prd.get("description_length",0)>=int(r.get("min_description_chars",100))
        dim_ok=not (r.get("requires_dimensions")=="true" and not prd.get("has_dimensions"))
        issues=sum([not img_ok, not desc_ok, not dim_ok])
        enriched.append({"product_id":prd["product_id"],"category":prd["category"],"images_ok":img_ok,"description_ok":desc_ok,"dimensions_ok":dim_ok,"compliance_issues":issues})
    (art/"enrich_branch_context_artifact.json").write_text(json.dumps({"enriched":enriched,"total":len(enriched)},indent=2)+"\n",encoding="utf-8")
    (art/"enrich_branch_context_status.json").write_text(json.dumps({"success":True,"enriched":len(enriched),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
