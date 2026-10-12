#!/usr/bin/env python3
"""Evaluate risk: check consent validity, sensitive data, sharing permissions."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,required=True); p.add_argument("--fixture",type=Path,required=True)
    a=p.parse_args(); art=a.workspace/"artifacts"
    ingested=json.loads((art/"ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    validated=json.loads((art/"validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    consents,policy=ingested["consents"],ingested["policy"]
    req_ver=policy["required_consent_version"]; rules=policy["risk_rules"]; scored=[]
    for r in validated["valid"]:
        sid=r["student_id"]; c=consents.get(sid,{})
        issues=[]; cs=r.get("consent_status","")
        if cs=="revoked": issues.append(rules["revoked_consent"])
        elif cs=="pending": issues.append(rules["pending_consent"])
        elif not c.get("data_sharing_consent"): issues.append("no_data_sharing_consent")
        if c.get("consent_version")!=req_ver: issues.append(f"outdated_consent_version: {c.get('consent_version')}!={req_ver}")
        if r.get("has_sensitive_data")=="true" and not c.get("data_sharing_consent"): issues.append(rules["sensitive_data_no_consent"])
        route="exception" if issues else "approved"
        scored.append({"student_id":sid,"student_name":r["student_name"],"consent_status":cs,
                       "has_sensitive":r.get("has_sensitive_data"),"risk_issues":issues,"route":route,"issue_count":len(issues)})
    approved=[s for s in scored if s["route"]=="approved"]; exceptions=[s for s in scored if s["route"]=="exception"]
    result={"scored":scored,"approved":approved,"exceptions":exceptions,"total":len(scored),"approved_count":len(approved),"exception_count":len(exceptions)}
    (art/"evaluate_policy_or_risk_artifact.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    (art/"evaluate_policy_or_risk_status.json").write_text(json.dumps({"success":True,"scored":len(scored),"approved":len(approved),"exceptions":len(exceptions),"errors":[]},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
