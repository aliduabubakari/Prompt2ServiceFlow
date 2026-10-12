#!/usr/bin/env python3
"""Validate and materialize the arrived transaction CSV."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


REQUIRED_COLUMNS = ["transaction_id", "customer_id", "amount", "currency", "transaction_date"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    destination = artifacts / "transactions.csv"
    shutil.copyfile(args.fixture, destination)
    with destination.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise SystemExit(f"missing required columns: {missing}")
    dataset = {"columns": columns, "rows": rows}
    (artifacts / "validated_dataset.json").write_text(
        json.dumps(dataset, indent=2) + "\n", encoding="utf-8"
    )
    data_object = {"source_uri": str(destination), "record_count": len(rows), "columns": columns}
    (artifacts / "validated_data_object.json").write_text(
        json.dumps(data_object, indent=2) + "\n", encoding="utf-8"
    )
    status = {"success": True, "rows_read": len(rows), "errors": []}
    (artifacts / "validation_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
