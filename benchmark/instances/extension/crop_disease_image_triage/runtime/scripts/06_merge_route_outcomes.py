#!/usr/bin/env python3
"""Merge route outcomes: combine approved and exception records into final disposition."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace; artifacts = root / "artifacts"

    approved = json.loads((artifacts / "route_approved_records_artifact.json").read_text(encoding="utf-8"))
    exceptions = json.loads((artifacts / "route_exception_records_artifact.json").read_text(encoding="utf-8"))

    merged = {
        "disposition": "complete",
        "summary": {
            "total_images": approved["total_routed"] + exceptions["total_escalated"],
            "approved": approved["total_routed"],
            "escalated": exceptions["total_escalated"],
        },
        "approved_records": [{"image_id": r["image_id"], "farmer_id": r["farmer_id"],
                               "crop_type": r["crop_type"], "risk_score": r.get("risk_score", "N/A"),
                               "reason": r.get("reason", "")} for r in approved["records"]],
        "exception_records": [{"image_id": r["image_id"], "farmer_id": r["farmer_id"],
                                "crop_type": r["crop_type"], "risk_score": r.get("risk_score", "N/A"),
                                "reason": r.get("reason", "")} for r in exceptions["records"]],
    }
    (artifacts / "merge_route_outcomes_artifact.json").write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    (artifacts / "merge_route_outcomes_status.json").write_text(
        json.dumps({"success": True, "merged": merged["summary"]["total_images"], "errors": []}, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
