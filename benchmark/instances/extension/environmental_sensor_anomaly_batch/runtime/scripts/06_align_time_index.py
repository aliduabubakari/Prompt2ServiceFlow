#!/usr/bin/env python3
"""Align time index: round timestamps to window boundaries, fill gaps, ensure consistent indexing."""
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
    batch_start = parse_ts(fixture["batch_window_start"])
    batch_end = parse_ts(fixture["batch_window_end"])

    metrics_data = json.loads(
        (artifacts / "compute_window_metrics_artifact.json").read_text(encoding="utf-8")
    )

    # Align each window's time boundaries to fixed grid
    aligned = []
    for m in metrics_data["per_window_metrics"]:
        ws = parse_ts(m["window_start"])
        we = parse_ts(m["window_end"])
        # Snap to fixed grid: round window_start down to nearest window boundary
        offset_minutes = int((ws - batch_start).total_seconds() / 60)
        grid_index = offset_minutes // window_minutes
        aligned_start = batch_start + timedelta(minutes=grid_index * window_minutes)
        aligned_end = aligned_start + timedelta(minutes=window_minutes)

        aligned.append({
            **m,
            "aligned_window_start": aligned_start.isoformat().replace("+00:00", "Z"),
            "aligned_window_end": aligned_end.isoformat().replace("+00:00", "Z"),
            "grid_index": grid_index,
            "is_aligned": aligned_start.isoformat() == ws.isoformat(),
        })

    # Detect gaps in time grid per station
    station_windows: dict[str, list[dict]] = {}
    for a in aligned:
        station_windows.setdefault(a["station_id"], []).append(a)

    gaps = []
    for sid, wins in station_windows.items():
        wins.sort(key=lambda w: w["grid_index"])
        for i in range(len(wins) - 1):
            expected_next = wins[i]["grid_index"] + 1
            actual_next = wins[i + 1]["grid_index"]
            if actual_next > expected_next:
                gaps.append({
                    "station_id": sid,
                    "gap_after_grid": wins[i]["grid_index"],
                    "expected_next_grid": expected_next,
                    "actual_next_grid": actual_next,
                    "missing_windows": actual_next - expected_next,
                })

    result = {
        "aligned_metrics": aligned,
        "time_grid": {
            "batch_start": fixture["batch_window_start"],
            "batch_end": fixture["batch_window_end"],
            "window_minutes": window_minutes,
            "total_grid_slots": int((batch_end - batch_start).total_seconds() / 60 / window_minutes),
        },
        "gaps_detected": gaps,
        "total_gaps": len(gaps),
    }
    (artifacts / "align_time_index_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "windows_aligned": len(aligned),
        "gaps_detected": len(gaps),
        "errors": [],
    }
    (artifacts / "align_time_index_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
