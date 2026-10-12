#!/usr/bin/env python3
"""Normalize Partition C: signature compliance — check required signatures by doc type."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    policy=ingested["policy"]; sig_required=policy["signature_required_types"]; norm_c=[]
    for d in validated["valid"]:
        needs_sig=d["doc_type"] in sig_required; has_sig=d["has_signatures"]
        sig_ok=not needs_sig or has_sig
        norm_c.append({"doc_id":d["doc_id"],"doc_type":d["doc_type"],"signature_required":needs_sig,
                       "has_signature":has_sig,"signature_compliant":sig_ok})
    (art/"normalize_partition_c_artifact.json").write_text(json.dumps({"partition":"C","records":norm_c,"total":len(norm_c)},indent=2)+"\n",encoding="utf-8")
    (art/"normalize_partition_c_status.json").write_text(json.dumps({"success":True,"normalized":len(norm_c),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
