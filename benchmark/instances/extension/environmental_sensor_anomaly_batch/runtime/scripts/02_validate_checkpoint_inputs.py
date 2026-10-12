#!/usr/bin/env python3
"""Validate checkpoint inputs: batch window, required fields, station existence, metric validity."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

REQUIRED_EVENT_FIELDS = {"sensor_id", "station_id", "timestamp", "metric", "value", "unit"}


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    ingested = json.loads(
        (artifacts / "ingest_bounded_events_artifact.json").read_text(encoding="utf-8")
    )
    events = ingested["events"]
    stations = ingested["stations"]
    threshold_policy = ingested["threshold_policy"]

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    batch_start = parse_ts(fixture["batch_window_start"])
    batch_end = parse_ts(fixture["batch_window_end"])
    required_metrics = set(threshold_policy.get("required_metrics", []))
    unknown_policy = threshold_policy.get("unknown_station_policy", "reject")

    errors = []
    valid_events = []
    for evt in events:
        issues = []
        # Required fields
        missing = REQUIRED_EVENT_FIELDS - set(evt.keys())
        if missing:
            issues.append(f"missing_fields: {', '.join(missing)}")

        # Timestamp within batch window
        try:
            ts = parse_ts(evt.get("timestamp", ""))
            if ts < batch_start or ts > batch_end:
                issues.append(f"timestamp_out_of_batch_window: {evt['timestamp']}")
        except (KeyError, ValueError) as e:
            issues.append(f"invalid_timestamp: {e}")

        # Station must exist in metadata
        sid = evt.get("station_id", "")
        if sid and sid not in stations and unknown_policy == "reject":
            issues.append(f"unknown_station: {sid}")

        # Metric must be in required list
        metric = evt.get("metric", "")
        if required_metrics and metric not in required_metrics:
            issues.append(f"unrecognized_metric: {metric}")

        if issues:
            errors.append({
                "message": "Validation failed",
                "event_id": evt.get("sensor_id", "?"),
                "line": evt.get("_line", None),
                "issues": issues,
            })
        else:
            valid_events.append(evt)

    result = {
        "valid_events": valid_events,
        "total_events": len(events),
        "valid_count": len(valid_events),
        "rejected_count": len(errors),
        "validation_errors": errors,
        "batch_window": {"start": fixture["batch_window_start"], "end": fixture["batch_window_end"]},
    }
    (artifacts / "validate_checkpoint_inputs_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "valid": len(valid_events),
        "rejected": len(errors),
        "errors": errors,
    }
    (artifacts / "validate_checkpoint_inputs_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
