#!/usr/bin/env python3
"""Send mock SMS campaign to regular segment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    segs = json.loads((artifacts / "customer_segments.json").read_text(encoding="utf-8"))

    regular = [r for r in segs["rows"] if r.get("segment") == "regular" and r.get("phone", "").strip()]

    results = {
        "campaign_sent": True,
        "recipients_targeted": len(regular),
        "segment": "regular",
        "channel": "sms",
        "errors": [],
    }
    (artifacts / "sms_campaign_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
