#!/usr/bin/env python3
"""Normalize: compute recognition rate and signature compliance."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    staged=json.loads((art/"stage_raw_artifacts_artifact.json").read_text(encoding="utf-8"))
    norm=[]
    for s in staged["staged"]:
        rec_rate=round(s["fields_recognized"]/max(s["field_count"],1)*100,1)
        sig_ok=not s.get("requires_sig") or s.get("has_signature")
        issues=sum([not sig_ok])
        norm.append({**s,"recognition_rate":rec_rate,"signature_ok":sig_ok,"issue_count":issues})
    (art/"normalize_records_artifact.json").write_text(json.dumps({"normalized":norm,"total":len(norm)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_records_status.json").write_text(json.dumps({"success":True,"normalized":len(norm),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
