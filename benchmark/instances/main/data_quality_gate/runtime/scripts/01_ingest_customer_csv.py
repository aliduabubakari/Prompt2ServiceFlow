#!/usr/bin/env python3
"""Profile a customer CSV and emit ingest metadata."""

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
    dataset_path = artifacts / "customers.csv"
    shutil.copyfile(args.fixture, dataset_path)
    with dataset_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    metadata = {
        "source_uri": str(dataset_path),
        "record_count": len(rows),
        "columns": columns,
        "parse_status": "success",
    }
    (artifacts / "ingested_data_object.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
