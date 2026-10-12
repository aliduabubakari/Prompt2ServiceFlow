#!/usr/bin/env python3
"""Mock population density enrichment: assign deterministic density values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MOCK_DENSITY = {
    "City Center Station": 8500,
    "Harbor Station": 3200,
    "Mountain Station": 450,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    source = json.loads((artifacts / "land_use_enriched_json.json").read_text(encoding="utf-8"))

    enriched_rows = []
    for row in source["rows"]:
        name = row.get("station_name", "")
        density = MOCK_DENSITY.get(name, 0)
        enriched_row = dict(row)
        enriched_row["population_density"] = density
        enriched_rows.append(enriched_row)

    columns = source["columns"] + ["population_density"]
    output = {
        "columns": columns,
        "rows": enriched_rows,
        "row_count": len(enriched_rows),
    }
    out_path = artifacts / "population_enriched_json.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    status = {
        "success": True,
        "rows_processed": len(enriched_rows),
        "rows_enriched": len(enriched_rows),
        "rows_failed": 0,
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "population_enrichment_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
