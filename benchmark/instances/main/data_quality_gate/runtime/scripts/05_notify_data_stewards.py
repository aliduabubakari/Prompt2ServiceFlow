#!/usr/bin/env python3
"""Record a deterministic mock email delivery receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    status = {
        "sent": True,
        "recipients": ["data-stewards@company.com"],
        "subject": "Data Quality Alert - Customer Data",
        "message_id": "mock-data-quality-alert-001",
        "errors": [],
    }
    artifacts = args.workspace / "artifacts"
    (artifacts / "notification_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
