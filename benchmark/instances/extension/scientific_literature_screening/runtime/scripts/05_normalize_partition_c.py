#!/usr/bin/env python3
"""Normalize C: reviewer matching — find eligible reviewers per article."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    reviewers=ingested["reviewers"]; norm=[]
    for article in validated["valid"]:
        art_kw=set(k.lower() for k in article.get("keywords",[]))
        matches=[]
        for rid,rev in reviewers.items():
            rev_exp=set(rev["expertise_keywords"].lower().split())
            if art_kw&rev_exp and rev["availability"]=="available":
                matches.append({"reviewer_id":rid,"name":rev["reviewer_name"],"max_articles":int(rev["max_articles"])})
        norm.append({"article_id":article["article_id"],"eligible_reviewers":matches,"reviewer_count":len(matches)})
    (art/"normalize_partition_c_artifact.json").write_text(json.dumps({"partition":"C","records":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_c_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
