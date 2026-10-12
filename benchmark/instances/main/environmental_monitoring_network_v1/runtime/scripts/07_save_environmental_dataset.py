#!/usr/bin/env python3
"""Export risk-scored tabular JSON to CSV."""

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
    source = json.loads((artifacts / "risk_scored_json.json").read_text(encoding="utf-8"))

    columns = source["columns"]
    rows = source["rows"]

    out_path = artifacts / "enriched_stations.csv"
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    status = {
        "success": True,
        "rows_read": len(rows),
        "rows_written": len(rows),
        "columns_exported": columns,
        "output_uri": str(out_path),
        "errors": [],
    }
    (artifacts / "export_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
