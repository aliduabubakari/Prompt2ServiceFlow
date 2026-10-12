#!/usr/bin/env python3
"""Compute per-window metrics with station-aware anomaly detection."""
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

    windows_data = json.loads(
        (artifacts / "build_analysis_windows_artifact.json").read_text(encoding="utf-8")
    )
    ingested = json.loads(
        (artifacts / "ingest_bounded_events_artifact.json").read_text(encoding="utf-8")
    )
    stations = ingested["stations"]
    windows = windows_data["windows"]

    metrics = []
    for w in windows:
        win_events = w["events"]
        station = stations.get(w["station_id"], {})
        thresholds = station.get("thresholds", {})
        metrics_seen = set(e.get("metric", "") for e in win_events)
        values = [e.get("value", 0) for e in win_events]

        # Determine max severity per metric against station thresholds
        anomaly_flags = []
        for e in win_events:
            metric = e.get("metric", "")
            value = e.get("value", 0)
            t = thresholds.get(metric, {})
            critical = t.get("critical_threshold")
            warning = t.get("warning_threshold")
            if critical is not None and value > critical:
                anomaly_flags.append("critical")
            elif warning is not None and value > warning:
                anomaly_flags.append("warning")

        max_severity = "normal"
        if "critical" in anomaly_flags:
            max_severity = "critical"
        elif "warning" in anomaly_flags:
            max_severity = "warning"

        metrics.append({
            "station_id": w["station_id"],
            "window_index": w["window_index"],
            "window_start": w["window_start"],
            "window_end": w["window_end"],
            "event_count": len(win_events),
            "metrics_observed": sorted(metrics_seen),
            "min_value": round(min(values), 2) if values else None,
            "max_value": round(max(values), 2) if values else None,
            "avg_value": round(sum(values) / len(values), 2) if values else None,
            "anomaly_severity": max_severity,
            "anomaly_count": len(anomaly_flags),
        })

    total_windows = len(metrics)
    warning_windows = sum(1 for m in metrics if m["anomaly_severity"] == "warning")
    critical_windows = sum(1 for m in metrics if m["anomaly_severity"] == "critical")

    result = {
        "per_window_metrics": metrics,
        "summary": {
            "total_windows": total_windows,
            "total_events": sum(m["event_count"] for m in metrics),
            "warning_windows": warning_windows,
            "critical_windows": critical_windows,
            "normal_windows": total_windows - warning_windows - critical_windows,
            "unique_stations": len(set(m["station_id"] for m in metrics)),
        },
    }
    (artifacts / "compute_window_metrics_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "windows_analyzed": total_windows,
        "errors": [],
    }
    (artifacts / "compute_window_metrics_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
