#!/usr/bin/env python3
"""Scan user-content CSV and emit structured scan dataset."""

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
    dest = artifacts / "user_content.csv"
    shutil.copyfile(args.fixture, dest)

    with dest.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        items = list(reader)
        columns = reader.fieldnames or []

    dataset = {
        "columns": columns,
        "items": items,
        "total_items": len(items),
    }
    (artifacts / "scanned_content_dataset.json").write_text(
        json.dumps(dataset, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "total_items": len(items),
        "parse_success": True,
        "errors": [],
    }
    (artifacts / "scan_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
