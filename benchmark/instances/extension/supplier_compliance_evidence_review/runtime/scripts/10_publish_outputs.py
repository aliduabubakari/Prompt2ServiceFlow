#!/usr/bin/env python3
"""Publish outputs: export redacted compliance report CSV, review packet, and audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--execution-time", type=str, default=None)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    execution_time = args.execution_time or "2026-07-20T09:00:00Z"
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))

    redacted_data = json.loads(
        (artifacts / "apply_redaction_or_suppression_artifact.json").read_text(encoding="utf-8")
    )
    fused_data = json.loads(
        (artifacts / "fuse_sources_artifact.json").read_text(encoding="utf-8")
    )
    review_packet = json.loads(
        (artifacts / "create_human_review_packet_artifact.json").read_text(encoding="utf-8")
    )

    # Build checkpoint manifest
    manifest = {
        "checkpoint_id": f"ckpt_supplier_compliance_{execution_time[:10].replace('-', '_')}",
        "checkpoint_time": execution_time,
        "pipeline_id": fixture["pipeline_id"],
        "compliance_summary": fused_data["summary"],
        "review_items": review_packet["total_suppliers_for_review"],
        "output_files": ["compliance_report.csv", "review_packet.json", "audit_manifest.json"],
        "status": "completed",
    }
    (artifacts / "audit_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Export redacted compliance CSV
    csv_rel = "compliance_report.csv"
    csv_path = artifacts / csv_rel
    fieldnames = [
        "supplier_id", "supplier_name", "tax_id", "bank_account",
        "country", "risk_tier", "compliance_status", "compliance_reason",
        "active_certs", "expired_certs", "escalated_for_review",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for s in redacted_data["redacted_suppliers"]:
            s["escalated_for_review"] = str(s["escalated_for_review"])
            writer.writerow(s)

    # Save review packet
    (artifacts / "review_packet.json").write_text(
        json.dumps(review_packet, indent=2) + "\n", encoding="utf-8"
    )

    publish_result = {
        "audit_manifest": manifest,
        "compliance_csv": csv_rel,
        "review_packet": "review_packet.json",
    }
    (artifacts / "publish_outputs_artifact.json").write_text(
        json.dumps(publish_result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "publish_outputs_status.json").write_text(
        json.dumps({"success": True, "csv_exported": csv_rel, "review_items": review_packet["total_suppliers_for_review"], "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
