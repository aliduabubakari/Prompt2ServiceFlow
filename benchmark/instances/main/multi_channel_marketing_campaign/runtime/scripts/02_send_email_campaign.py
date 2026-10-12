#!/usr/bin/env python3
"""Send mock email campaign to premium segment."""

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

    premium = [r for r in segs["rows"] if r.get("segment") == "premium" and r.get("email", "").strip()]

    results = {
        "campaign_sent": True,
        "recipients_targeted": len(premium),
        "segment": "premium",
        "channel": "email",
        "errors": [],
    }
    (artifacts / "email_campaign_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
