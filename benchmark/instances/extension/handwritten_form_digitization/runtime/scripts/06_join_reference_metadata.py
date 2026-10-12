#!/usr/bin/env python3
"""Join reference: route to department queue based on confidence and issues."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    visual=json.loads((art/"extract_visual_text_features_artifact.json").read_text(encoding="utf-8"))
    joined=[]
    for v in visual["visual"]:
        queue=v.get("routing_queue","auto_process")
        if v.get("needs_manual"): queue="manual_review"
        joined.append({**v,"final_queue":queue})
    (art/"join_reference_metadata_artifact.json").write_text(json.dumps({"joined":joined,"total":len(joined)},indent=2)+"\n",encoding="utf-8")
    (art/"join_reference_metadata_status.json").write_text(json.dumps({"success":True,"joined":len(joined),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
