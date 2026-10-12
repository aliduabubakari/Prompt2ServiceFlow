#!/usr/bin/env python3
"""Sort sensor events by timestamp and deduplicate by sensor_id."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    validated = json.loads(
        (artifacts / "validate_checkpoint_inputs_artifact.json").read_text(encoding="utf-8")
    )
    events = validated["valid_events"]

    # Sort by timestamp, then sensor_id
    events.sort(key=lambda e: (e.get("timestamp", ""), e.get("sensor_id", "")))

    # Deduplicate by sensor_id
    seen = set()
    deduped = []
    dups = []
    for evt in events:
        sid = evt.get("sensor_id", "")
        if sid in seen:
            dups.append({"sensor_id": sid, "line": evt.get("_line", "?")})
        else:
            seen.add(sid)
            deduped.append(evt)

    result = {
        "events": deduped,
        "total_before_dedup": len(events),
        "total_after_dedup": len(deduped),
        "duplicates_removed": len(dups),
        "duplicate_details": dups,
    }
    (artifacts / "sort_and_deduplicate_records_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "sorted_and_deduped": len(deduped),
        "duplicates_removed": len(dups),
        "errors": [],
    }
    (artifacts / "sort_and_deduplicate_records_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
