#!/usr/bin/env python3
"""Mock geocoding: assign deterministic coordinates based on station name."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MOCK_COORDS = {
    "City Center Station": (40.7128, -74.0060),
    "Harbor Station": (37.7749, -122.4194),
    "Mountain Station": (39.7392, -104.9903),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    source = json.loads((artifacts / "formatted_stations_json.json").read_text(encoding="utf-8"))

    enriched_rows = []
    for row in source["rows"]:
        name = row.get("station_name", "")
        lat, lon = MOCK_COORDS.get(name, (0.0, 0.0))
        enriched_row = dict(row)
        enriched_row["latitude"] = lat
        enriched_row["longitude"] = lon
        enriched_rows.append(enriched_row)

    columns = source["columns"] + ["latitude", "longitude"]
    output = {
        "columns": columns,
        "rows": enriched_rows,
        "row_count": len(enriched_rows),
        "geocoding": {
            "provider_id": "geocodingHere",
            "method": "fixture_mock",
        },
    }
    out_path = artifacts / "geocoded_stations_json.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    status = {
        "success": True,
        "geocoder_id": "geocodingHere",
        "rows_processed": len(enriched_rows),
        "rows_geocoded": len(enriched_rows),
        "rows_failed": 0,
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "geocoding_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
