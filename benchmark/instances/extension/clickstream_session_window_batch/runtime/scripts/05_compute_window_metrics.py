#!/usr/bin/env python3
"""Compute per-window metrics: event counts, unique pages, durations, conversion flags."""
from __future__ import annotations
import argparse, json
from datetime import datetime
from pathlib import Path

def parse_ts(ts: str):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    windows_data = json.loads(
        (artifacts / "build_analysis_windows_artifact.json").read_text(encoding="utf-8")
    )
    windows = windows_data["windows"]

    metrics = []
    for w in windows:
        events = w["events"]
        event_types = [e.get("event_type", "unknown") for e in events]
        pages = set(e.get("page_url", "") for e in events)
        devices = set(e.get("device_type", "unknown") for e in events)

        start = parse_ts(w["window_start"])
        end = parse_ts(w["window_end"])
        duration_seconds = (end - start).total_seconds()

        conversion = any(
            et in ("checkout_start", "add_to_cart") for et in event_types
        )

        metrics.append({
            "session_id": w["session_id"],
            "window_index": w["window_index"],
            "user_id": w["user_id"],
            "event_count": len(events),
            "unique_pages": len(pages),
            "devices_used": sorted(devices),
            "event_types_seen": sorted(set(event_types)),
            "duration_seconds": round(duration_seconds, 1),
            "has_conversion_signal": conversion,
            "window_start": w["window_start"],
            "window_end": w["window_end"],
        })

    # Aggregate summary
    total_events = sum(m["event_count"] for m in metrics)
    total_windows = len(metrics)
    conversion_windows = sum(1 for m in metrics if m["has_conversion_signal"])

    result = {
        "per_window_metrics": metrics,
        "summary": {
            "total_windows": total_windows,
            "total_events": total_events,
            "conversion_windows": conversion_windows,
            "conversion_rate": round(conversion_windows / total_windows, 3) if total_windows else 0,
            "avg_events_per_window": round(total_events / total_windows, 1) if total_windows else 0,
            "unique_users": len(set(m["user_id"] for m in metrics)),
        },
    }
    (artifacts / "compute_window_metrics_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {"success": True, "windows_analyzed": total_windows, "metrics_computed": len(metrics), "errors": []}
    (artifacts / "compute_window_metrics_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
