#!/usr/bin/env python3
"""Filesystem-backed mock of the AirVisual dimensional PostgreSQL loader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TABLES = [
    "factairvisualtable",
    "dimDateTimeTable",
    "dimLocationTable",
    "dimMainPollutionTable",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--pollution-mapping", type=Path, required=True)
    parser.add_argument("--weather-mapping", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    observation = json.loads(
        (artifacts / "validated_airvisual_observation.json").read_text(encoding="utf-8")
    )
    pollution_mapping = json.loads(args.pollution_mapping.read_text(encoding="utf-8"))
    weather_mapping = json.loads(args.weather_mapping.read_text(encoding="utf-8"))
    pollution = observation["pollution"]
    weather = observation["weather"]
    row = {
        "timestamp": pollution["ts"],
        "city": observation["city"],
        "state": observation["state"],
        "country": observation["country"],
        "longitude": observation["coordinates"][0],
        "latitude": observation["coordinates"][1],
        "aqius": pollution["aqius"],
        "main_pollution": pollution_mapping[pollution["mainus"]],
        "temperature_c": weather["tp"],
        "weather": weather_mapping[weather["ic"]],
    }
    mock_database = args.workspace / "mock_postgres"
    mock_database.mkdir(parents=True, exist_ok=True)
    (mock_database / "factairvisualtable.json").write_text(
        json.dumps([row], indent=2) + "\n", encoding="utf-8"
    )
    loaded_tables = {"tables": [{"name": name, "role": "fact" if name.startswith("fact") else "dimension"} for name in TABLES]}
    (artifacts / "loaded_tables.json").write_text(
        json.dumps(loaded_tables, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "tables": TABLES,
        "rows_inserted": 1,
        "rows_upserted": 3,
        "rows_skipped": 0,
        "duplicate_found": False,
        "errors": [],
    }
    (artifacts / "dimensional_load_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
