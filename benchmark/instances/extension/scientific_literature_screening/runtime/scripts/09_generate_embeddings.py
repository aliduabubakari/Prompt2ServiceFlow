#!/usr/bin/env python3
"""Generate embeddings: assign relevance score based on keyword match strength."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    chunked=json.loads((art/"chunk_documents_artifact.json").read_text(encoding="utf-8"))
    embedded=[]
    for c in chunked["chunked"]:
        kc=c.get("keyword_match_count",0)
        relevance=round(min(kc/3,1.0)*100,1)
        embedded.append({**c,"relevance_score":relevance,"screening_decision":"include" if relevance>=33 else "exclude"})
    (art/"generate_embeddings_artifact.json").write_text(json.dumps({"embedded":embedded,"total":len(embedded)},indent=2)+"\n",encoding="utf-8")
    (art/"generate_embeddings_status.json").write_text(json.dumps({"success":True,"embedded":len(embedded),"include":sum(1 for e in embedded if e["screening_decision"]=="include"),"exclude":sum(1 for e in embedded if e["screening_decision"]=="exclude"),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
