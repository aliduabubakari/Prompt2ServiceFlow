#!/usr/bin/env python3
"""Normalize B: keyword matching score against eligibility criteria."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    req_kw=set(ingested["criteria"]["required_keywords"]); norm=[]
    for article in validated["valid"]:
        art_kw=set(article.get("keywords",[])); matched=art_kw&req_kw
        norm.append({"article_id":article["article_id"],"matched_keywords":sorted(matched),"keyword_match_count":len(matched)})
    (art/"normalize_partition_b_artifact.json").write_text(json.dumps({"partition":"B","records":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_b_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
