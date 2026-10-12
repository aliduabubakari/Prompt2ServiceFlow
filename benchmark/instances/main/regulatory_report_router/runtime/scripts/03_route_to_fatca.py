#!/usr/bin/env python3
"""Generate FATCA regulatory report."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); a=p.parse_args()
    art=a.workspace/"artifacts"
    ds=json.loads((art/"transaction_dataset.json").read_text(encoding="utf-8"))
    intl=[r for r in ds["rows"] if r.get("account_type")=="international"]
    content=f"FATCA REPORT\nTransactions: {len(intl)}\n"+"\n".join(f"  {r['transaction_id']}: {r['amount']} {r['currency']}" for r in intl)
    report={"report_content":content,"report_profile":"fatca","transaction_count":len(intl)}
    (art/"fatca_report.txt").write_text(content,encoding="utf-8")
    (art/"fatca_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    st={"success":True,"errors":[]}
    (art/"fatca_report_status.json").write_text(json.dumps(st,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
