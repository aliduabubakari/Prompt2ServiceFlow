#!/usr/bin/env python3
"""Publish outputs: generate CSV of aligned metrics, anomaly alert digest, and checkpoint manifest."""
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

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    execution_time = args.execution_time or fixture.get("batch_window_end", "2026-07-20T09:00:00Z")

    aligned_data = json.loads(
        (artifacts / "align_time_index_artifact.json").read_text(encoding="utf-8")
    )
    metrics_data = json.loads(
        (artifacts / "compute_window_metrics_artifact.json").read_text(encoding="utf-8")
    )

    # Build checkpoint manifest
    manifest = {
        "checkpoint_id": f"ckpt_env_sensor_{execution_time[:10].replace('-', '_')}",
        "checkpoint_time": execution_time,
        "batch_window": {
            "start": fixture["batch_window_start"],
            "end": fixture["batch_window_end"],
        },
        "pipeline_id": fixture["pipeline_id"],
        "execution_summary": metrics_data["summary"],
        "time_alignment": {
            "windows_aligned": aligned_data["total_gaps"] == 0,
            "gaps_detected": aligned_data["total_gaps"],
        },
        "output_files": ["aligned_metrics.csv", "alert_digest.json", "checkpoint_manifest.json"],
        "status": "completed",
    }
    (artifacts / "checkpoint_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Export aligned metrics CSV
    csv_rel = "aligned_metrics.csv"
    csv_path = artifacts / csv_rel
    fieldnames = [
        "station_id", "window_index", "aligned_window_start", "aligned_window_end",
        "event_count", "min_value", "max_value", "avg_value",
        "anomaly_severity", "anomaly_count",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for m in aligned_data["aligned_metrics"]:
            writer.writerow(m)

    # Build alert digest for anomalous windows
    alerts = [
        {
            "station_id": m["station_id"],
            "window_start": m["aligned_window_start"],
            "severity": m["anomaly_severity"],
            "anomaly_count": m["anomaly_count"],
        }
        for m in aligned_data["aligned_metrics"]
        if m["anomaly_severity"] != "normal"
    ]
    alert_digest = {
        "generated_at": execution_time,
        "total_alerts": len(alerts),
        "alerts": alerts,
    }
    (artifacts / "alert_digest.json").write_text(
        json.dumps(alert_digest, indent=2) + "\n", encoding="utf-8"
    )

    publish_result = {
        "checkpoint_manifest": manifest,
        "metrics_csv": csv_rel,
        "alert_digest": "alert_digest.json",
        "output_summary": metrics_data["summary"],
    }
    (artifacts / "publish_outputs_artifact.json").write_text(
        json.dumps(publish_result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "csv_exported": csv_rel,
        "alerts_generated": len(alerts),
        "errors": [],
    }
    (artifacts / "publish_outputs_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
