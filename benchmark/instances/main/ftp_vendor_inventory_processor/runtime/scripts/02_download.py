#!/usr/bin/env python3
"""Mock FTP download — writes placeholder vendor CSV."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    (art/"vendor_inventory.csv").write_text("sku,quantity,price\nSKU-A,100,12.50\nSKU-B,50,8.00\n",encoding="utf-8")
    (art/"downloaded_file.bin").write_bytes(b"vendor_inventory.csv\n")
    (art/"transfer_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
