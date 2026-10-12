#!/usr/bin/env python3
"""Validate checkpoint inputs: batch boundaries, required identifiers, consent, and checkpoint continuity."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_EVENT_FIELDS = {"event_id", "user_id", "session_id", "timestamp", "event_type"}


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
    consent = ingested["user_consent"]
    previous_checkpoint = ingested.get("previous_checkpoint", {})

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    batch_start = parse_ts(fixture["batch_window_start"])
    batch_end = parse_ts(fixture["batch_window_end"])

    errors = []
    valid_events = []

    # Validate checkpoint continuity
    prev_ckpt_id = previous_checkpoint.get("checkpoint_id", "")
    if prev_ckpt_id:
        prev_ckpt_end = previous_checkpoint.get("batch_window_end", "")
        if prev_ckpt_end:
            prev_end = parse_ts(prev_ckpt_end)
            if prev_end > batch_start:
                errors.append({
                    "message": "Previous checkpoint end is after current batch start",
                    "previous_checkpoint_end": prev_ckpt_end,
                    "batch_window_start": fixture["batch_window_start"],
                })

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

        # User consent check
        uid = evt.get("user_id", "")
        consent_entry = consent.get(uid)
        if consent_entry and consent_entry["consent_status"] == "revoked":
            issues.append(f"user_consent_revoked: {uid}")

        if issues:
            errors.append({
                "message": "Validation failed",
                "event_id": evt.get("event_id", "?"),
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
        "previous_checkpoint_id": previous_checkpoint.get("checkpoint_id", ""),
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
