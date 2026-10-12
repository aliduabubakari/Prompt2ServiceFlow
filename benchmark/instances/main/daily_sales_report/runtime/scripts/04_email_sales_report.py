#!/usr/bin/env python3
"""Record a deterministic mock email delivery receipt with attachment metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"

    # Check which attachments exist
    attachments = []
    if (artifacts / "sales_report.csv").is_file():
        attachments.append("sales_report.csv")
    if (artifacts / "sales_chart.pdf").is_file():
        attachments.append("sales_chart.pdf")

    status = {
        "sent": True,
        "recipients": ["management@company.com"],
        "subject": "Daily Sales Report - 2024-01-15",
        "attachments": attachments,
        "errors": [],
    }
    (artifacts / "notification_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
