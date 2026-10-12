#!/usr/bin/env python3
"""Ingest station CSV and produce structured tabular JSON with metadata."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    dest = artifacts / "stations.csv"
    shutil.copyfile(args.fixture, dest)

    with dest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []

    output = {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "dataset_id": "2",
        "table_name": "JOT_",
        "date_column": "installation_date",
    }
    out_path = artifacts / "formatted_stations_json.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    status = {
        "success": True,
        "rows_read": len(rows),
        "rows_written": len(rows),
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "format_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
