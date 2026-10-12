#!/usr/bin/env python3
"""Generate mock document parquet data (as JSON)."""
from __future__ import annotations
import argparse, json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    docs=[{"doc_id":f"D{i:03d}","title":f"Document {i}","content":f"This is document {i} about machine learning and NLP keywords extraction."} for i in range(1,6)]
    (art/"documents.parquet").write_text(json.dumps({"columns":["doc_id","title","content"],"rows":docs},indent=2)+"\n",encoding="utf-8")
    (art/"gen_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
