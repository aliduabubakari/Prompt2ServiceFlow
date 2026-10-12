#!/usr/bin/env python3
"""Publish outputs: export triage CSV, exception notification, and audit manifest."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--execution-time", type=str, default=None)
    args = parser.parse_args()
    root = args.workspace; artifacts = root / "artifacts"
    execution_time = args.execution_time or "2026-07-20T12:00:00Z"
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))

    merged = json.loads((artifacts / "merge_route_outcomes_artifact.json").read_text(encoding="utf-8"))

    manifest = {"checkpoint_id": f"ckpt_crop_triage_{execution_time[:10].replace('-', '_')}",
                "checkpoint_time": execution_time, "pipeline_id": fixture["pipeline_id"],
                "triage_summary": merged["summary"],
                "output_files": ["crop_triage_report.csv", "exception_alert.json", "audit_manifest.json"],
                "status": "completed"}
    (artifacts / "audit_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    csv_rel = "crop_triage_report.csv"
    with (artifacts / csv_rel).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image_id", "farmer_id", "crop_type", "risk_score", "route", "reason"])
        w.writeheader()
        for g in [merged["approved_records"], merged["exception_records"]]:
            for r in g:
                w.writerow({**r, "route": "approved" if r in merged["approved_records"] else "exception"})

    alert = {"generated_at": execution_time, "escalated_count": merged["summary"]["escalated"],
             "exception_images": [r["image_id"] for r in merged["exception_records"]]}
    (artifacts / "exception_alert.json").write_text(json.dumps(alert, indent=2) + "\n", encoding="utf-8")

    (artifacts / "publish_outputs_artifact.json").write_text(
        json.dumps({"audit_manifest": manifest, "triage_csv": csv_rel, "exception_alert": "exception_alert.json"}, indent=2) + "\n",
        encoding="utf-8")
    (artifacts / "publish_outputs_status.json").write_text(
        json.dumps({"success": True, "csv_exported": csv_rel, "escalated": alert["escalated_count"], "errors": []}, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
