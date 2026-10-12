#!/usr/bin/env python3
"""Extract text: classify article by text completeness and flag full-text availability."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    fused=json.loads((art/"fuse_partitions_artifact.json").read_text(encoding="utf-8"))
    articles_lookup={a["article_id"]:a for a in ingested["articles"]}
    extracted=[]
    for f in fused["fused"]:
        orig=articles_lookup.get(f["article_id"],{})
        extracted.append({**f,"has_full_text":orig.get("has_full_text",False),
                          "abstract_complete":orig.get("abstract_word_count",0)>=100})
    (art/"extract_or_parse_text_artifact.json").write_text(json.dumps({"extracted":extracted,"total":len(extracted)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_or_parse_text_status.json").write_text(json.dumps({"success":True,"extracted":len(extracted),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
