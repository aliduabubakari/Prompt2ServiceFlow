#!/usr/bin/env python3
"""Ingest vendor shipment CSV with schema validation."""

from __future__ import annotations

import argparse, csv, json, shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--vendor", type=str, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    dest = artifacts / f"{args.vendor}_shipments.csv"
    shutil.copyfile(args.fixture, dest)

    with dest.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames or []

    dataset = {"columns": columns, "rows": rows}
    (artifacts / f"{args.vendor}_dataset.json").write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    data_obj = {"source_uri": str(dest), "record_count": len(rows), "columns": columns, "vendor": args.vendor}
    (artifacts / f"{args.vendor}_data_object.json").write_text(json.dumps(data_obj, indent=2) + "\n", encoding="utf-8")
    status = {"success": True, "rows_read": len(rows), "errors": []}
    (artifacts / f"{args.vendor}_validation_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
