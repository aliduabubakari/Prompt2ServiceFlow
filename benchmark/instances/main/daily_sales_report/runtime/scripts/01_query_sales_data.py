#!/usr/bin/env python3
"""Mock PostgreSQL query that returns deterministic daily sales data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MOCK_SALES = [
    {"date": "2024-01-15", "product": "Widget A", "daily_sales": 1500.50},
    {"date": "2024-01-15", "product": "Widget B", "daily_sales": 2300.00},
    {"date": "2024-01-15", "product": "Widget C", "daily_sales": 975.25},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    columns = ["date", "product", "daily_sales"]
    result = {
        "columns": columns,
        "rows": MOCK_SALES,
    }
    (artifacts / "sales_query_result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    status = {
        "success": True,
        "rows_returned": len(MOCK_SALES),
        "errors": [],
    }
    (artifacts / "query_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
