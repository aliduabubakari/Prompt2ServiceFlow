#!/usr/bin/env python3
"""Validate source contracts: check schemas, cross-reference stores/locations, weather coverage."""
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED_WEATHER_FIELDS = {"city", "date", "temp_c", "weather_condition"}
REQUIRED_SALES_FIELDS = {"store_id", "city", "date", "revenue", "transactions"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    ingested = json.loads((artifacts / "ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    weather_obs = ingested["weather"]["observations"]
    sales = ingested["sales"]
    locations = ingested["locations"]

    errors = []

    # Validate weather observations
    valid_weather = []
    for obs in weather_obs:
        missing = REQUIRED_WEATHER_FIELDS - set(obs.keys())
        if missing:
            errors.append({"record": obs, "issues": [f"missing_fields: {missing}"]})
        else:
            valid_weather.append(obs)

    # Validate sales rows
    valid_sales = []
    orphan_stores = set()
    weather_index = {(w["city"], w["date"]): w for w in valid_weather}
    for row in sales:
        issues = []
        missing = REQUIRED_SALES_FIELDS - set(row.keys())
        if missing:
            issues.append(f"missing_fields: {missing}")

        sid = row.get("store_id", "")
        if sid not in locations:
            issues.append(f"store_not_in_locations: {sid}")
            orphan_stores.add(sid)

        city_date = (row.get("city", ""), row.get("date", ""))
        if city_date not in weather_index:
            issues.append(f"no_weather_data_for: {city_date}")

        if issues:
            errors.append({"record": row, "issues": issues})
        else:
            valid_sales.append(row)

    result = {
        "valid_weather": valid_weather,
        "valid_sales": valid_sales,
        "total_errors": len(errors),
        "errors": errors,
        "orphan_stores": sorted(orphan_stores),
        "weather_coverage": len(weather_index),
    }
    (artifacts / "validate_source_contract_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "validate_source_contract_status.json").write_text(
        json.dumps({"success": True, "errors_found": len(errors), "errors": errors}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
