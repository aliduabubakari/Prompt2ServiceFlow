#!/usr/bin/env python3
"""Merge: combine features, enrichment, quality scores."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    feats=json.loads((art/"extract_branch_features_artifact.json").read_text(encoding="utf-8"))
    enr=json.loads((art/"enrich_branch_context_artifact.json").read_text(encoding="utf-8"))
    scor=json.loads((art/"score_branch_quality_artifact.json").read_text(encoding="utf-8"))
    fm={r["product_id"]:r for r in feats["features"]}; em={r["product_id"]:r for r in enr["enriched"]}; sm={r["product_id"]:r for r in scor["scores"]}
    merged=[]
    for pid in fm:
        m={**fm[pid]}; e=em.get(pid,{}); s=sm.get(pid,{})
        for k,v in e.items():
            if k!="product_id": m[k]=v
        for k,v in s.items():
            if k!="product_id": m[k]=v
        merged.append(m)
    (art/"merge_branch_outputs_artifact.json").write_text(json.dumps({"merged":merged,"total":len(merged)},indent=2)+"\n",encoding="utf-8")
    (art/"merge_branch_outputs_status.json").write_text(json.dumps({"success":True,"merged":len(merged),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
