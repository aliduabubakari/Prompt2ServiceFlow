#!/usr/bin/env python3
"""Merge branch outputs: combine features, enrichment, and quality scores per claim."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    features=json.loads((art/"extract_branch_features_artifact.json").read_text(encoding="utf-8"))
    enriched=json.loads((art/"enrich_branch_context_artifact.json").read_text(encoding="utf-8"))
    scores=json.loads((art/"score_branch_quality_artifact.json").read_text(encoding="utf-8"))
    fmap={f["claim_id"]:f for f in features["features"]}
    emap={e["claim_id"]:e for e in enriched["enriched"]}
    smap={s["claim_id"]:s for s in scores["scores"]}
    merged=[]
    for cid in fmap:
        merged.append({**fmap[cid],**{f"enrich_{k}":v for k,v in emap.get(cid,{}).items() if k!="claim_id"},
                       **{f"quality_{k}":v for k,v in smap.get(cid,{}).items() if k!="claim_id"}})
    (art/"merge_branch_outputs_artifact.json").write_text(json.dumps({"merged":merged,"total":len(merged)},indent=2)+"\n",encoding="utf-8")
    (art/"merge_branch_outputs_status.json").write_text(json.dumps({"success":True,"merged":len(merged),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
