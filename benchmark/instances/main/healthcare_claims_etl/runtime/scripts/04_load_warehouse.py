#!/usr/bin/env python3
"""Mock load transformed dataset to analytics warehouse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    transformed = json.loads(
        (artifacts / "transformed_healthcare_dataset.json").read_text(encoding="utf-8")
    )

    warehouse = args.workspace / "mock_warehouse"
    warehouse.mkdir(parents=True, exist_ok=True)
    (warehouse / "claims_fact.json").write_text(
        json.dumps(transformed["rows"], indent=2) + "\n", encoding="utf-8"
    )
    provider_ids = list({r["provider_id"] for r in transformed["rows"]})
    (warehouse / "providers_dim.json").write_text(
        json.dumps([{"provider_id": pid} for pid in provider_ids], indent=2) + "\n",
        encoding="utf-8",
    )

    loaded_tables = {
        "tables": [
            {"name": "healthcare_analytics.claims_fact", "rows": len(transformed["rows"])},
            {"name": "healthcare_analytics.providers_dim", "rows": len(provider_ids)},
        ]
    }
    (artifacts / "loaded_tables.json").write_text(
        json.dumps(loaded_tables, indent=2) + "\n", encoding="utf-8"
    )
    status = {"success": True, "tables_loaded": 2, "errors": []}
    (artifacts / "warehouse_load_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
