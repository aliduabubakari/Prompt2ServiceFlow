#!/usr/bin/env python3
"""Transform tabular query result to CSV."""

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
    result = json.loads((artifacts / "sales_query_result.json").read_text(encoding="utf-8"))

    columns = result["columns"]
    rows = result["rows"]

    csv_path = artifacts / "sales_report.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    status = {
        "success": True,
        "rows_written": len(rows),
        "output_uri": str(csv_path),
        "errors": [],
    }
    (artifacts / "transform_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
