#!/usr/bin/env python3
"""Observe a mock dated input file without sleeping through the timeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--file-location", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    location = json.loads(args.file_location.read_text(encoding="utf-8"))
    available = args.fixture.is_file()
    decision = {
        "available": available,
        "path": str(args.fixture),
        "configured_location": location["path"],
        "reason": "fixture_present" if available else "fixture_missing_before_timeout",
    }
    (artifacts / "availability_decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "availability.txt").write_text("true" if available else "false", encoding="utf-8")
    status = {"success": True, "available": available, "errors": []}
    (artifacts / "check_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
