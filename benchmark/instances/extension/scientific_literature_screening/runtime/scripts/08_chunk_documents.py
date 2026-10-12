#!/usr/bin/env python3
"""Chunk documents: estimate reading time and assign article complexity."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    extracted=json.loads((art/"extract_or_parse_text_artifact.json").read_text(encoding="utf-8"))
    chunked=[]
    for e in extracted["extracted"]:
        wc=e.get("abstract_word_count",250) if "abstract_word_count" in str(e) else 250
        chunked.append({**e,"estimated_reading_min":round(wc/200,1),"complexity":"high" if wc>250 else ("medium" if wc>150 else "low")})
    (art/"chunk_documents_artifact.json").write_text(json.dumps({"chunked":chunked,"total":len(chunked)},indent=2)+"\n",encoding="utf-8")
    (art/"chunk_documents_status.json").write_text(json.dumps({"success":True,"chunked":len(chunked),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
