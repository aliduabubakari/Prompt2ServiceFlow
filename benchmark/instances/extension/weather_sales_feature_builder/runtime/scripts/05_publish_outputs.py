#!/usr/bin/env python3
"""Publish outputs: feature CSV, anomaly report, and checkpoint manifest."""
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

    normalized_data = json.loads((artifacts / "normalize_records_artifact.json").read_text(encoding="utf-8"))

    manifest = {
        "checkpoint_id": f"ckpt_weather_sales_{execution_time[:10].replace('-', '_')}",
        "checkpoint_time": execution_time,
        "pipeline_id": fixture["pipeline_id"],
        "feature_summary": {
            "total_features": normalized_data["feature_count"],
            "anomalies_detected": normalized_data["anomalies_detected"],
        },
        "output_files": ["weather_sales_features.csv", "feature_manifest.json"],
        "status": "completed",
    }
    (artifacts / "feature_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Export features CSV
    csv_rel = "weather_sales_features.csv"
    csv_path = artifacts / csv_rel
    fieldnames = [
        "store_id", "city", "date", "revenue", "transactions", "top_category",
        "temp_c", "weather_condition", "temp_impact",
        "precipitation_mm", "rain_impact",
        "store_size_sqm", "store_type", "revenue_per_sqm", "weather_anomaly",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in normalized_data["normalized_features"]:
            r["weather_anomaly"] = str(r["weather_anomaly"])
            writer.writerow(r)

    publish_result = {
        "feature_manifest": manifest,
        "features_csv": csv_rel,
    }
    (artifacts / "publish_outputs_artifact.json").write_text(
        json.dumps(publish_result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "publish_outputs_status.json").write_text(
        json.dumps({"success": True, "csv_exported": csv_rel, "features": normalized_data["feature_count"],
                     "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
