#!/usr/bin/env python3
"""Publish outputs: generate checkpoint manifest referencing previous checkpoint, export CSV metrics."""
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

    # Use fixed execution time from scenario or fixture
    execution_time = args.execution_time or fixture.get("batch_window_end", "2026-07-20T09:00:00Z")

    # Load upstream artifacts
    metrics_data = json.loads(
        (artifacts / "compute_window_metrics_artifact.json").read_text(encoding="utf-8")
    )
    validated = json.loads(
        (artifacts / "validate_checkpoint_inputs_artifact.json").read_text(encoding="utf-8")
    )
    previous_checkpoint_id = validated.get("previous_checkpoint_id", "")

    # Build checkpoint manifest with fixed timestamp
    manifest = {
        "checkpoint_id": f"ckpt_{fixture['pipeline_id']}_{execution_time[:10].replace('-', '_')}",
        "checkpoint_time": execution_time,
        "previous_checkpoint_id": previous_checkpoint_id,
        "batch_window": {
            "start": fixture["batch_window_start"],
            "end": fixture["batch_window_end"],
        },
        "pipeline_id": fixture["pipeline_id"],
        "execution_summary": metrics_data["summary"],
        "output_files": [
            "per_window_metrics.csv",
            "checkpoint_manifest.json",
        ],
        "status": "completed",
    }

    (artifacts / "checkpoint_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Export per-window metrics as CSV (relative path only in manifest)
    csv_rel = "per_window_metrics.csv"
    csv_path = artifacts / csv_rel
    fieldnames = [
        "session_id", "window_index", "user_id", "event_count",
        "unique_pages", "duration_seconds", "has_conversion_signal",
        "window_start", "window_end",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for m in metrics_data["per_window_metrics"]:
            writer.writerow({
                **m,
                "has_conversion_signal": str(m["has_conversion_signal"]),
            })

    # Publish output bundle — use relative paths
    publish_result = {
        "checkpoint_manifest": manifest,
        "metrics_csv": csv_rel,
        "output_summary": metrics_data["summary"],
    }
    (artifacts / "publish_outputs_artifact.json").write_text(
        json.dumps(publish_result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "manifest_written": True,
        "csv_exported": csv_rel,
        "errors": [],
    }
    (artifacts / "publish_outputs_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
