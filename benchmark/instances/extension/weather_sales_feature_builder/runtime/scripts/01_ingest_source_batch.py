#!/usr/bin/env python3
"""Ingest weather API snapshot, store sales CSV, and store location table."""
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
    execution_time = args.execution_time or "2026-07-20T09:00:00Z"

    # Weather JSON
    weather = json.loads((fixtures_dir / fixture["inputs"]["weather"]).read_text(encoding="utf-8"))

    # Store sales CSV
    sales = []
    with (fixtures_dir / fixture["inputs"]["sales"]).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            row["revenue"] = float(row["revenue"])
            row["transactions"] = int(row["transactions"])
            sales.append(row)

    # Store locations CSV
    locations = {}
    with (fixtures_dir / fixture["inputs"]["locations"]).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            row["size_sqm"] = int(row["size_sqm"])
            locations[row["store_id"]] = row

    result = {
        "weather": weather,
        "sales": sales,
        "locations": locations,
        "total_weather_obs": len(weather["observations"]),
        "total_sales_rows": len(sales),
        "total_locations": len(locations),
        "ingested_at": execution_time,
    }
    (artifacts / "ingest_source_batch_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "ingest_source_batch_status.json").write_text(
        json.dumps({"success": True, "weather_obs": len(weather["observations"]),
                     "sales_rows": len(sales), "locations": len(locations), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
