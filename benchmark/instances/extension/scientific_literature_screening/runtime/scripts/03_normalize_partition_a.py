#!/usr/bin/env python3
"""Normalize A: article metadata — title, journal, year, study type, author count."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    norm=[]
    for article in validated["valid"]:
        norm.append({"article_id":article["article_id"],"title":article["title"],"journal":article["journal"],
                     "year":article["year"],"study_type":article["study_type"],"author_count":len(article.get("authors",[]))})
    (art/"normalize_partition_a_artifact.json").write_text(json.dumps({"partition":"A","records":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_a_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
