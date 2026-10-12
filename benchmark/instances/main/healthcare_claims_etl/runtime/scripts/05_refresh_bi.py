#!/usr/bin/env python3
"""Mock BI dashboard refresh trigger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"

    notification = {
        "refresh_triggered": True,
        "target": "healthcare_claims_overview",
        "message": "BI dashboard refresh initiated for healthcare_claims_overview",
    }
    (artifacts / "refresh_notification.json").write_text(
        json.dumps(notification, indent=2) + "\n", encoding="utf-8"
    )
    status = {"success": True, "refresh_attempted": True, "errors": []}
    (artifacts / "refresh_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
