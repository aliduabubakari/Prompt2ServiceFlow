#!/usr/bin/env python3
"""Score branch quality: grade image quality."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    fx=json.loads(a.fixture.read_text(encoding="utf-8")); grades=fx["quality_grades"]
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    scored=[]
    for prd in validated["valid"]:
        q=prd["image_quality_score"]
        g="excellent" if q>=grades["excellent"] else ("good" if q>=grades["good"] else "poor")
        scored.append({"product_id":prd["product_id"],"image_quality":q,"quality_grade":g})
    (art/"score_branch_quality_artifact.json").write_text(json.dumps({"scores":scored,"total":len(scored)},indent=2)+"\n",encoding="utf-8")
    (art/"score_branch_quality_status.json").write_text(json.dumps({"success":True,"scored":len(scored),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
