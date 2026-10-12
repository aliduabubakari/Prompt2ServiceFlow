#!/usr/bin/env python3
"""Build analysis windows: group events into session windows by (user_id, session_id) pair."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    gap_minutes = fixture.get("session_window_gap_minutes", 30)

    sorted_data = json.loads(
        (artifacts / "sort_and_deduplicate_records_artifact.json").read_text(encoding="utf-8")
    )
    events = sorted_data["events"]

    # Group events by (user_id, session_id) to prevent cross-user session merging
    sessions: dict[tuple[str, str], list[dict]] = {}
    for evt in events:
        key = (evt.get("user_id", "?"), evt.get("session_id", "unknown"))
        if key not in sessions:
            sessions[key] = []
        sessions[key].append(evt)

    # Build windows per (user_id, session_id) group
    windows = []
    for (uid, sid), sevents in sessions.items():
        # Sort within group by timestamp
        sevents.sort(key=lambda e: parse_ts(e.get("timestamp", "1970-01-01T00:00:00Z")))

        # Split into sub-windows if gap > gap_minutes
        current_window: list[dict] = []
        window_index = 0
        for evt in sevents:
            if not current_window:
                current_window.append(evt)
            else:
                last_ts = parse_ts(current_window[-1]["timestamp"])
                curr_ts = parse_ts(evt["timestamp"])
                gap = (curr_ts - last_ts).total_seconds() / 60.0
                if gap > gap_minutes:
                    windows.append({
                        "session_id": sid,
                        "window_index": window_index,
                        "user_id": uid,
                        "events": current_window,
                        "event_count": len(current_window),
                        "window_start": current_window[0]["timestamp"],
                        "window_end": current_window[-1]["timestamp"],
                    })
                    window_index += 1
                    current_window = [evt]
                else:
                    current_window.append(evt)
        if current_window:
            windows.append({
                "session_id": sid,
                "window_index": window_index,
                "user_id": uid,
                "events": current_window,
                "event_count": len(current_window),
                "window_start": current_window[0]["timestamp"],
                "window_end": current_window[-1]["timestamp"],
            })

    result = {
        "windows": windows,
        "total_windows": len(windows),
        "total_sessions": len(sessions),
        "gap_threshold_minutes": gap_minutes,
    }
    (artifacts / "build_analysis_windows_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "windows_built": len(windows),
        "sessions_processed": len(sessions),
        "errors": [],
    }
    (artifacts / "build_analysis_windows_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
