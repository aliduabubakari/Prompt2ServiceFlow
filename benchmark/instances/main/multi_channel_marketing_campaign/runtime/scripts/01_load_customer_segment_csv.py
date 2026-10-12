#!/usr/bin/env python3
"""Load customer segment CSV and emit structured dataset."""

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
    dest = artifacts / "customer_segments.csv"
    shutil.copyfile(args.fixture, dest)

    with dest.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames or []

    dataset = {"columns": columns, "rows": rows}
    (artifacts / "customer_segments.json").write_text(
        json.dumps(dataset, indent=2) + "\n", encoding="utf-8"
    )
    status = {"success": True, "rows_loaded": len(rows), "errors": []}
    (artifacts / "load_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
