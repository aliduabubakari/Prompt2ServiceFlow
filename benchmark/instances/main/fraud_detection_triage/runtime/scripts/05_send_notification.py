#!/usr/bin/env python3
"""Record a deterministic mock email delivery receipt at the merge point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execution-time", type=str, default=None)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    exec_ts = args.execution_time or "unknown"

    # Check which branch completed
    manual_path = artifacts / "manual_review_status.json"
    auto_path = artifacts / "auto_approval_status.json"
    branch_info = []
    if manual_path.is_file():
        branch_info.append("manual_review")
    if auto_path.is_file():
        branch_info.append("auto_approve")

    status = {
        "sent": True,
        "recipients": ["fraud-team@company.com"],
        "subject": "Fraud Detection Triage Complete",
        "message_id": f"mock-fraud-triage-{'-'.join(branch_info)}-{exec_ts[:10]}",
        "execution_time": exec_ts,
        "errors": [],
    }
    (artifacts / "notification_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
