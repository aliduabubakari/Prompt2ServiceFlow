#!/usr/bin/env python3
"""Fixture-backed mock of the AirVisual nearest-city extractor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    response = json.loads(args.fixture.read_text(encoding="utf-8"))
    output_path = artifacts / "raw_airvisual_response.json"
    output_path.write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    status = {
        "action": "fetched",
        "success": True,
        "duplicate_check_enabled": True,
        "duplicate_found": False,
        "endpoint_url": "http://api.airvisual.com/v2/nearest_city",
        "http_status_code": 200,
        "latitude": 13.79059242,
        "longitude": 100.32622308,
        "city": "Salaya",
        "state": "Nakhon Pathom",
        "country": "Thailand",
        "output_path": str(output_path),
        "error": None,
    }
    (artifacts / "extraction_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
