#!/usr/bin/env python3
"""Extract branch features: price tier, image sufficiency, description completeness."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    features=[]
    for prd in validated["valid"]:
        price_tier="premium" if prd["price"]>100 else ("mid" if prd["price"]>30 else "budget")
        features.append({"product_id":prd["product_id"],"price":prd["price"],"price_tier":price_tier,
                         "image_count":prd["image_count"],"description_length":prd["description_length"]})
    (art/"extract_branch_features_artifact.json").write_text(json.dumps({"features":features,"total":len(features)},indent=2)+"\n",encoding="utf-8")
    (art/"extract_branch_features_status.json").write_text(json.dumps({"success":True,"extracted":len(features),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
