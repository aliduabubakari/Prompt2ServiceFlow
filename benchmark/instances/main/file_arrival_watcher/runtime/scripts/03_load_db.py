#!/usr/bin/env python3
"""Load the schema-validated transaction CSV into a local database mock."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--database-resource", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    with (artifacts / "transactions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    resource = json.loads(args.database_resource.read_text(encoding="utf-8"))
    database = args.workspace / "mock_postgres"
    database.mkdir(parents=True, exist_ok=True)
    (database / "transactions.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    reference = {"target_table": "public.transactions", "rows_imported": len(rows), "driver": resource["driver"]}
    (artifacts / "target_db_reference.json").write_text(
        json.dumps(reference, indent=2) + "\n", encoding="utf-8"
    )
    status = {"success": True, "rows_loaded": len(rows), "errors": []}
    (artifacts / "load_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
