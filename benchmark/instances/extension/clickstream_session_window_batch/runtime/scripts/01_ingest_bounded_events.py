#!/usr/bin/env python3
"""Ingest bounded clickstream events, user consent table, and previous checkpoint manifest."""
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

    # Use fixed execution time from scenario or fall back to fixture batch end
    execution_time = args.execution_time or fixture.get("batch_window_end", "2026-07-20T09:00:00Z")

    # Read clickstream events JSONL
    events_path = fixtures_dir / fixture["inputs"]["events"]
    events = []
    parse_errors = []
    with events_path.open(encoding="utf-8") as f:
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

    # Read user consent CSV
    consent_path = fixtures_dir / fixture["inputs"]["consent"]
    consent_map = {}
    with consent_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            consent_map[row["user_id"]] = {
                "consent_status": row["consent_status"],
                "consent_date": row["consent_date"],
            }

    # Read previous checkpoint manifest
    checkpoint_path = fixtures_dir / fixture["inputs"]["checkpoint"]
    previous_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    result = {
        "events": events,
        "user_consent": consent_map,
        "previous_checkpoint": previous_checkpoint,
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
        "errors": parse_errors,
    }
    (artifacts / "ingest_bounded_events_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
