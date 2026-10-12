#!/usr/bin/env python3
"""Mock GraphQL: create customer."""
from __future__ import annotations
import argparse, json
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--op",type=str,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"; art.mkdir(parents=True,exist_ok=True)
    if a.op=="create":
        resp={"data":{"createCustomerV2":{"customer":{"id":1,"email":"test@example.com"}}},"success":True}
        (art/"create_response.json").write_text(json.dumps(resp,indent=2)+"\n",encoding="utf-8")
        (art/"create_result.json").write_text(json.dumps({"customer_id":1},indent=2)+"\n",encoding="utf-8")
        (art/"create_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
    elif a.op=="token":
        resp={"data":{"generateCustomerToken":{"token":"mock-token-abc123"}},"success":True}
        (art/"token_response.json").write_text(json.dumps(resp,indent=2)+"\n",encoding="utf-8")
        (art/"token_result.json").write_text(json.dumps({"token":"mock-token-abc123"},indent=2)+"\n",encoding="utf-8")
        (art/"token_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
    elif a.op=="get":
        resp={"data":{"customer":{"id":1,"firstname":"John","lastname":"Doe","email":"test@example.com"}},"success":True}
        (art/"get_response.json").write_text(json.dumps(resp,indent=2)+"\n",encoding="utf-8")
        (art/"get_result.json").write_text(json.dumps({"name":"John Doe"},indent=2)+"\n",encoding="utf-8")
        (art/"get_status.json").write_text(json.dumps({"success":True,"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
