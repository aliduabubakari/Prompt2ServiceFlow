#!/usr/bin/env python3
"""Send mock summary email with ETL processing results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    ctx = json.loads((artifacts / "etl_summary_context.json").read_text(encoding="utf-8"))

    summary = {
        "summary_text": f"Supply Chain Shipment ETL completed. Rows loaded: {ctx['rows_loaded']}.",
        "context_fields": {"rows_loaded": ctx["rows_loaded"], "load_success": ctx["load_success"]},
    }
    (artifacts / "rendered_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    status = {
        "sent": True,
        "recipients": ["supply-chain-team@company.com"],
        "subject": "Daily Supply Chain Shipment ETL Summary",
        "errors": [],
    }
    (artifacts / "notification_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
