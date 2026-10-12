#!/usr/bin/env python3
"""Fuse sources: merge normalized records with policy rules to produce compliance status per supplier."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    normalized_data = json.loads((artifacts / "normalize_sources_artifact.json").read_text(encoding="utf-8"))
    reference = json.loads((artifacts / "ingest_reference_source_artifact.json").read_text(encoding="utf-8"))
    policy = reference["policy"]

    risk_rules = policy["risk_tier_thresholds"]
    cert_min = policy["certificate_requirements"]["min_active_certs"]

    fused = []
    for s in normalized_data["normalized_suppliers"]:
        # Determine compliance status
        if s["total_certs"] == 0:
            compliance = "non_compliant"
            reason = "no_certificates"
        elif s["active_certs"] < cert_min:
            compliance = "non_compliant"
            reason = "no_active_certificates"
        elif s["expired_certs"] > 0:
            compliance = "at_risk"
            reason = "has_expired_certificates"
        else:
            compliance = "compliant"
            reason = "all_requirements_met"

        # Risk-tier escalation
        risk_action = risk_rules.get(s["risk_tier"], "flag_for_review")
        escalated = risk_action == "auto_escalate" or compliance == "non_compliant"

        fused.append({
            **s,
            "compliance_status": compliance,
            "compliance_reason": reason,
            "risk_action": risk_action,
            "escalated_for_review": escalated,
        })

    result = {
        "fused_suppliers": fused,
        "summary": {
            "total": len(fused),
            "compliant": sum(1 for f in fused if f["compliance_status"] == "compliant"),
            "at_risk": sum(1 for f in fused if f["compliance_status"] == "at_risk"),
            "non_compliant": sum(1 for f in fused if f["compliance_status"] == "non_compliant"),
            "escalated": sum(1 for f in fused if f["escalated_for_review"]),
        },
    }
    (artifacts / "fuse_sources_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "fuse_sources_status.json").write_text(
        json.dumps({"success": True, "fused": len(fused), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
