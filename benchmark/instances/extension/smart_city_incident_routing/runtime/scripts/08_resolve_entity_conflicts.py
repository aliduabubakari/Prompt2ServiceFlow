#!/usr/bin/env python3
"""Resolve entity conflicts: flag duplicate-like incidents, conflicting priorities."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    std=json.loads((art/"standardize_cross_domain_entities_artifact.json").read_text(encoding="utf-8"))
    resolved=[]; seen_types={}
    for s in std["standardized"]:
        conflict=seen_types.get(s["type"])
        seen_types[s["type"]]=s["incident_id"]
        resolved.append({**s,"potential_duplicate":bool(conflict),"conflict_with":conflict or ""})
    (art/"resolve_entity_conflicts_artifact.json").write_text(json.dumps({"resolved":resolved,"total":len(resolved)},indent=2)+"\n",encoding="utf-8")
    (art/"resolve_entity_conflicts_status.json").write_text(json.dumps({"success":True,"resolved":len(resolved),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
