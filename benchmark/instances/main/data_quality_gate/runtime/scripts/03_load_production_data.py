#!/usr/bin/env python3
"""Filesystem-backed mock of the production database loader."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    metadata = json.loads((artifacts / "ingested_data_object.json").read_text(encoding="utf-8"))
    with Path(metadata["source_uri"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    database = args.workspace / "mock_database"
    database.mkdir(parents=True, exist_ok=True)
    (database / "customers.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    status = {
        "success": True,
        "target_table": "customers",
        "rows_read": len(rows),
        "rows_written": len(rows),
        "write_mode": "upsert",
        "errors": [],
    }
    (artifacts / "production_load_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
