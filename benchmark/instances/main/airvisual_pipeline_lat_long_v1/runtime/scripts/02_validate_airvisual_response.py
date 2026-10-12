#!/usr/bin/env python3
"""Validate the required AirVisual nearest-city response fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    response = json.loads((artifacts / "raw_airvisual_response.json").read_text(encoding="utf-8"))
    data = response.get("data", {})
    location = data.get("location", {})
    current = data.get("current", {})
    required = {
        "status": response.get("status"),
        "city": data.get("city"),
        "state": data.get("state"),
        "country": data.get("country"),
        "coordinates": location.get("coordinates"),
        "pollution": current.get("pollution"),
        "weather": current.get("weather"),
    }
    missing = [name for name, value in required.items() if value in (None, "", [], {})]
    valid = response.get("status") == "success" and not missing
    result = {
        "valid": valid,
        "checked_schema": "airvisual_nearest_city_response/v1",
        "errors": [] if valid else ["Missing or invalid required fields"],
        "missing_fields": missing,
        "record_count": 1 if valid else 0,
    }
    (artifacts / "validation_result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if not valid:
        raise SystemExit("AirVisual response failed validation")
    observation = {
        "city": data["city"],
        "state": data["state"],
        "country": data["country"],
        "coordinates": location["coordinates"],
        "pollution": current["pollution"],
        "weather": current["weather"],
        "source_status": response["status"],
    }
    (artifacts / "validated_airvisual_observation.json").write_text(
        json.dumps(observation, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
