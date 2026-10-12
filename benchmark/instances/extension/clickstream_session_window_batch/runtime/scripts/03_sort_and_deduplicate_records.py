#!/usr/bin/env python3
"""Sort events by timestamp and deduplicate by event_id."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def parse_ts(ts: str):
    from datetime import datetime
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

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

    # Sort by timestamp, then by event_id for deterministic ordering
    events.sort(key=lambda e: (e.get("timestamp", ""), e.get("event_id", "")))

    # Deduplicate by event_id, keeping first occurrence
    seen = set()
    deduped = []
    dups = []
    for evt in events:
        eid = evt.get("event_id", "")
        if eid in seen:
            dups.append({"event_id": eid, "line": evt.get("_line", "?")})
        else:
            seen.add(eid)
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
    status = {"success": True, "sorted_and_deduped": len(deduped), "duplicates_removed": len(dups), "errors": []}
    (artifacts / "sort_and_deduplicate_records_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
