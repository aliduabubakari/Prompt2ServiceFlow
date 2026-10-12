#!/usr/bin/env python3
"""Fuse partitions: combine A+B+C into unified incident records."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    pa=json.loads((art/"normalize_partition_a_artifact.json").read_text(encoding="utf-8"))
    pb=json.loads((art/"normalize_partition_b_artifact.json").read_text(encoding="utf-8"))
    pc=json.loads((art/"normalize_partition_c_artifact.json").read_text(encoding="utf-8"))
    am={r["incident_id"]:r for r in pa["records"]}; bm={r["incident_id"]:r for r in pb["records"]}
    cm={r["incident_id"]:r for r in pc["records"]}; fused=[]
    for iid in am: fused.append({**am[iid],**bm.get(iid,{}),**cm.get(iid,{})})
    (art/"fuse_partitions_artifact.json").write_text(json.dumps({"fused":fused,"total":len(fused)},indent=2)+"\n",encoding="utf-8")
    (art/"fuse_partitions_status.json").write_text(json.dumps({"success":True,"fused":len(fused),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
