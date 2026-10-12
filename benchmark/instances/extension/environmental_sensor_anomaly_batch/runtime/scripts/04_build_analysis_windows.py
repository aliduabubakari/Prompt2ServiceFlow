#!/usr/bin/env python3
"""Build analysis windows: group sensor events into fixed-size windows by station."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timedelta
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
    window_minutes = fixture.get("window_size_minutes", 15)

    sorted_data = json.loads(
        (artifacts / "sort_and_deduplicate_records_artifact.json").read_text(encoding="utf-8")
    )
    events = sorted_data["events"]

    # Group events by station_id
    station_events: dict[str, list[dict]] = {}
    for evt in events:
        sid = evt.get("station_id", "unknown")
        if sid not in station_events:
            station_events[sid] = []
        station_events[sid].append(evt)

    # Build fixed-size windows per station
    windows = []
    batch_start = parse_ts(fixture["batch_window_start"])
    batch_end = parse_ts(fixture["batch_window_end"])

    for sid, sevents in station_events.items():
        sevents.sort(key=lambda e: parse_ts(e.get("timestamp", "1970-01-01T00:00:00Z")))
        # Build windows of window_minutes from batch_start
        window_start = batch_start
        window_index = 0
        while window_start < batch_end:
            window_end = window_start + timedelta(minutes=window_minutes)
            win_events = [
                e for e in sevents
                if window_start <= parse_ts(e["timestamp"]) < window_end
            ]
            if win_events:
                windows.append({
                    "station_id": sid,
                    "window_index": window_index,
                    "window_start": window_start.isoformat().replace("+00:00", "Z"),
                    "window_end": window_end.isoformat().replace("+00:00", "Z"),
                    "events": win_events,
                    "event_count": len(win_events),
                })
            window_start = window_end
            window_index += 1

    result = {
        "windows": windows,
        "total_windows": len(windows),
        "total_stations": len(station_events),
        "window_size_minutes": window_minutes,
    }
    (artifacts / "build_analysis_windows_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "windows_built": len(windows),
        "stations_processed": len(station_events),
        "errors": [],
    }
    (artifacts / "build_analysis_windows_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
