#!/usr/bin/env python3
"""Mock land-use classification: assign type based on station name."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MOCK_LAND_USE = {
    "City Center Station": "urban_high_density",
    "Harbor Station": "coastal_industrial",
    "Mountain Station": "forested_rural",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    source = json.loads((artifacts / "weather_enriched_json.json").read_text(encoding="utf-8"))

    enriched_rows = []
    for row in source["rows"]:
        name = row.get("station_name", "")
        land_use = MOCK_LAND_USE.get(name, "unknown")
        enriched_row = dict(row)
        enriched_row["land_use_type"] = land_use
        enriched_rows.append(enriched_row)

    columns = source["columns"] + ["land_use_type"]
    output = {
        "columns": columns,
        "rows": enriched_rows,
        "row_count": len(enriched_rows),
    }
    out_path = artifacts / "land_use_enriched_json.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    status = {
        "success": True,
        "rows_processed": len(enriched_rows),
        "rows_classified": len(enriched_rows),
        "rows_failed": 0,
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "land_use_classification_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
