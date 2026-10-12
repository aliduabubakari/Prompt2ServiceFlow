#!/usr/bin/env python3
"""Create human review packet: bundle escalated/non-compliant suppliers for manual review."""
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

    redacted_data = json.loads(
        (artifacts / "apply_redaction_or_suppression_artifact.json").read_text(encoding="utf-8")
    )

    # Select suppliers that need human review
    review_candidates = [
        s for s in redacted_data["redacted_suppliers"]
        if s["escalated_for_review"]
    ]

    packet = {
        "packet_id": "HRP-2026-07-20-001",
        "generated_at": "2026-07-20T09:00:00Z",
        "total_suppliers_for_review": len(review_candidates),
        "review_items": [
            {
                "supplier_id": s["supplier_id"],
                "supplier_name": s["supplier_name"],
                "compliance_status": s["compliance_status"],
                "compliance_reason": s["compliance_reason"],
                "risk_tier": s["risk_tier"],
                "risk_action": s["risk_action"],
                "cert_summary": f"{s['active_certs']} active, {s['expired_certs']} expired",
            }
            for s in review_candidates
        ],
    }
    (artifacts / "create_human_review_packet_artifact.json").write_text(
        json.dumps(packet, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "create_human_review_packet_status.json").write_text(
        json.dumps({"success": True, "review_items": len(review_candidates), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
