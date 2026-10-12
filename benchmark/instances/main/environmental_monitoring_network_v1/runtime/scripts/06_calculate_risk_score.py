#!/usr/bin/env python3
"""Compute composite environmental risk score from precipitation, density, and land use."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

LAND_USE_RISK = {
    "urban_high_density": 0.8,
    "coastal_industrial": 0.6,
    "forested_rural": 0.3,
    "unknown": 0.5,
}


def compute_risk(rain: float, density: int, land_use: str) -> float:
    precip_factor = min(rain / 100.0, 1.0) * 0.4
    density_factor = min(density / 10000.0, 1.0) * 0.3
    land_factor = LAND_USE_RISK.get(land_use, 0.5) * 0.3
    return round(precip_factor + density_factor + land_factor, 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    source = json.loads((artifacts / "population_enriched_json.json").read_text(encoding="utf-8"))

    enriched_rows = []
    for row in source["rows"]:
        rain = float(row.get("precipitation_sum", 0))
        density = int(row.get("population_density", 0))
        land_use = row.get("land_use_type", "unknown")
        score = compute_risk(rain, density, land_use)
        enriched_row = dict(row)
        enriched_row["risk_score"] = score
        enriched_rows.append(enriched_row)

    columns = source["columns"] + ["risk_score"]
    output = {
        "columns": columns,
        "rows": enriched_rows,
        "row_count": len(enriched_rows),
    }
    out_path = artifacts / "risk_scored_json.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    status = {
        "success": True,
        "rows_processed": len(enriched_rows),
        "rows_scored": len(enriched_rows),
        "output_column": "risk_score",
        "profile_id": "environmentalRiskCalculator",
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "risk_scoring_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
