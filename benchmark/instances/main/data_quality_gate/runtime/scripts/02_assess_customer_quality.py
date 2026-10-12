#!/usr/bin/env python3
"""Compute deterministic completeness and validity quality metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--threshold", type=float, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    metadata = json.loads((artifacts / "ingested_data_object.json").read_text(encoding="utf-8"))
    with Path(metadata["source_uri"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    cells = [value.strip() for row in rows for value in row.values()]
    completeness = 100.0 * sum(bool(value) for value in cells) / len(cells)
    valid_ids = sum(bool(row["customer_id"].strip()) for row in rows)
    valid_emails = sum("@" in row["email"] and "." in row["email"].split("@")[-1] for row in rows)
    validity = 100.0 * (valid_ids + valid_emails) / (2 * len(rows))
    overall = round((completeness + validity) / 2, 2)
    passed = overall >= args.threshold
    decision = {
        "completeness_score": round(completeness, 2),
        "validity_score": round(validity, 2),
        "overall_score": overall,
        "pass_threshold": args.threshold,
        "passed": passed,
        "route": "production" if passed else "quarantine",
        "record_count": len(rows),
    }
    (artifacts / "quality_decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "quality_route.txt").write_text(decision["route"], encoding="utf-8")


if __name__ == "__main__":
    main()
