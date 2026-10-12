#!/usr/bin/env python3
"""Mock load cleansed shipment data to inventory database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    ds = json.loads((artifacts / "cleansed_shipment_dataset.json").read_text(encoding="utf-8"))

    db = args.workspace / "mock_inventory_db"
    db.mkdir(parents=True, exist_ok=True)
    (db / "inventory_shipments.json").write_text(json.dumps(ds["rows"], indent=2) + "\n", encoding="utf-8")

    status = {"success": True, "rows_written": len(ds["rows"]), "errors": []}
    (artifacts / "db_load_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    ctx = {"rows_loaded": len(ds["rows"]), "load_success": True}
    (artifacts / "etl_summary_context.json").write_text(json.dumps(ctx, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
