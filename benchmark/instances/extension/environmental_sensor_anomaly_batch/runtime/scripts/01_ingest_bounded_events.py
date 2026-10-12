#!/usr/bin/env python3
"""Ingest bounded environmental sensor telemetry, station metadata, and anomaly threshold policy."""
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
    artifacts.mkdir(parents=True, exist_ok=True)

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    fixtures_dir = args.fixture.parent
    execution_time = args.execution_time or fixture.get("batch_window_end", "2026-07-20T09:00:00Z")

    # Read sensor telemetry JSONL
    telemetry_path = fixtures_dir / fixture["inputs"]["telemetry"]
    events = []
    parse_errors = []
    with telemetry_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                evt["_line"] = i
                events.append(evt)
            except json.JSONDecodeError as e:
                parse_errors.append({"line": i, "message": str(e)})

    # Read station metadata CSV
    stations_path = fixtures_dir / fixture["inputs"]["stations"]
    stations = {}
    with stations_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["station_id"]
            if sid not in stations:
                stations[sid] = {"station_name": row["station_name"], "thresholds": {}}
            stations[sid]["thresholds"][row["metric"]] = {
                "warning_threshold": float(row["warning_threshold"]),
                "critical_threshold": float(row["critical_threshold"]),
            }

    # Read threshold policy
    policy_path = fixtures_dir / fixture["inputs"]["policy"]
    threshold_policy = json.loads(policy_path.read_text(encoding="utf-8"))

    result = {
        "events": events,
        "stations": stations,
        "threshold_policy": threshold_policy,
        "total_events_read": len(events),
        "parse_errors": parse_errors,
        "ingested_at": execution_time,
    }
    (artifacts / "ingest_bounded_events_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": len(parse_errors) == 0,
        "events_ingested": len(events),
        "stations_loaded": len(stations),
        "errors": parse_errors,
    }
    (artifacts / "ingest_bounded_events_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
