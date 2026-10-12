#!/usr/bin/env python3
"""Mock weather enrichment: append deterministic weather variables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MOCK_WEATHER = {
    "City Center Station": {
        "apparent_temperature_max": 28.5,
        "apparent_temperature_min": 18.2,
        "precipitation_sum": 12.4,
        "precipitation_hours": 3.0,
    },
    "Harbor Station": {
        "apparent_temperature_max": 22.0,
        "apparent_temperature_min": 14.5,
        "precipitation_sum": 45.8,
        "precipitation_hours": 8.0,
    },
    "Mountain Station": {
        "apparent_temperature_max": 15.3,
        "apparent_temperature_min": 2.1,
        "precipitation_sum": 78.9,
        "precipitation_hours": 12.0,
    },
}
VARIABLES = [
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "precipitation_hours",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    source = json.loads((artifacts / "geocoded_stations_json.json").read_text(encoding="utf-8"))

    enriched_rows = []
    for row in source["rows"]:
        name = row.get("station_name", "")
        weather = MOCK_WEATHER.get(name, {v: 0 for v in VARIABLES})
        enriched_row = dict(row)
        enriched_row.update(weather)
        enriched_rows.append(enriched_row)

    columns = source["columns"] + VARIABLES
    output = {
        "columns": columns,
        "rows": enriched_rows,
        "row_count": len(enriched_rows),
    }
    out_path = artifacts / "weather_enriched_json.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    status = {
        "success": True,
        "rows_processed": len(enriched_rows),
        "rows_enriched": len(enriched_rows),
        "variables_requested": VARIABLES,
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "weather_enrichment_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
