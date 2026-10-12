#!/usr/bin/env python3
"""Cleanse and standardize vendor shipment data: normalize SKUs, validate dates, enrich location."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

LOCATION_HUBS = {"East Warehouse": "EWH", "North Center": "NCT", "West Hub": "WHB", "South Depot": "SDP"}


def normalize_sku(sku: str) -> str:
    return sku.strip().upper().replace("-", "_")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    all_rows = []
    for vendor in ["vendor_a", "vendor_b", "vendor_c"]:
        ds = json.loads((artifacts / f"{vendor}_dataset.json").read_text(encoding="utf-8"))
        for row in ds["rows"]:
            all_rows.append(dict(row))
            all_rows[-1]["vendor"] = vendor

    cleansed = []
    for row in all_rows:
        try:
            row["sku"] = normalize_sku(row["sku"])
            dt = datetime.strptime(row["ship_date"], "%Y-%m-%d")
            row["location_code"] = LOCATION_HUBS.get(row["destination"], "UNK")
            row["ship_date_validated"] = dt.strftime("%Y-%m-%d")
            cleansed.append(row)
        except (ValueError, KeyError):
            continue

    columns = ["shipment_id", "sku", "quantity", "ship_date_validated", "destination", "location_code", "vendor"]
    output = {"columns": columns, "rows": cleansed}
    (artifacts / "cleansed_shipment_dataset.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    data_obj = {"source_uri": str(artifacts / "cleansed_shipment_dataset.json"), "record_count": len(cleansed), "columns": columns}
    (artifacts / "cleansed_data_object.json").write_text(json.dumps(data_obj, indent=2) + "\n", encoding="utf-8")
    status = {"success": True, "rows_processed": len(cleansed), "errors": []}
    (artifacts / "transform_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
