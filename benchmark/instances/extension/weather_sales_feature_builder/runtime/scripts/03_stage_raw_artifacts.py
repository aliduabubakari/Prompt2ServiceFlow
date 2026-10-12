#!/usr/bin/env python3
"""Stage raw artifacts: join sales with weather and locations into auditable staging records."""
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

    validated = json.loads((artifacts / "validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    ingested = json.loads((artifacts / "ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    locations = ingested["locations"]

    weather_index = {(w["city"], w["date"]): w for w in validated["valid_weather"]}
    staged = []

    for sale in validated["valid_sales"]:
        city_date = (sale["city"], sale["date"])
        weather = weather_index.get(city_date, {})
        store = locations.get(sale["store_id"], {})

        staged.append({
            "store_id": sale["store_id"],
            "city": sale["city"],
            "date": sale["date"],
            "revenue": sale["revenue"],
            "transactions": sale["transactions"],
            "top_category": sale.get("top_category", ""),
            "temp_c": weather.get("temp_c"),
            "humidity_pct": weather.get("humidity_pct"),
            "precipitation_mm": weather.get("precipitation_mm", 0),
            "weather_condition": weather.get("weather_condition", "unknown"),
            "store_size_sqm": store.get("size_sqm"),
            "store_type": store.get("store_type", ""),
            "latitude": store.get("latitude"),
            "longitude": store.get("longitude"),
        })

    result = {
        "staged_records": staged,
        "total_staged": len(staged),
        "staging_timestamp": "2026-07-20T09:00:00Z",
    }
    (artifacts / "stage_raw_artifacts_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "stage_raw_artifacts_status.json").write_text(
        json.dumps({"success": True, "records_staged": len(staged), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
