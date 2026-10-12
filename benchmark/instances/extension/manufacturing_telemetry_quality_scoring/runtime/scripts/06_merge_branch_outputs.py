#!/usr/bin/env python3
"""Merge branches: combine features, enrichment, and quality scores."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def key(r): return (r["machine_id"],r["shift"])
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    feats=json.loads((art/"extract_branch_features_artifact.json").read_text(encoding="utf-8"))
    enr=json.loads((art/"enrich_branch_context_artifact.json").read_text(encoding="utf-8"))
    scor=json.loads((art/"score_branch_quality_artifact.json").read_text(encoding="utf-8"))
    fm={key(f):f for f in feats["features"]}; em={key(e):e for e in enr["enriched"]}; sm={key(s):s for s in scor["scores"]}
    merged=[]
    for k in fm:
        m={**fm[k]}
        if k in em: m.update({kk:vv for kk,vv in em[k].items() if kk not in ("machine_id","shift")})
        if k in sm: m.update({kk:vv for kk,vv in sm[k].items() if kk not in ("machine_id","shift")})
        merged.append(m)
    (art/"merge_branch_outputs_artifact.json").write_text(json.dumps({"merged":merged,"total":len(merged)},indent=2)+"\n",encoding="utf-8")
    (art/"merge_branch_outputs_status.json").write_text(json.dumps({"success":True,"merged":len(merged),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
