#!/usr/bin/env python3
"""Compare regenerated paper tables with the packaged publication bundle."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


CSV_FILES = (
    "primary_run_level.csv",
    "primary_instance_level.csv",
    "primary_summary.csv",
    "primary_split_sensitivity.csv",
    "primary_gate_summary.csv",
    "primary_gate_survival.csv",
    "primary_paired_effects.csv",
    "primary_failure_modes.csv",
    "ablation_run_level.csv",
    "ablation_instance_level.csv",
    "ablation_summary.csv",
    "ablation_paired_effects.csv",
    "stage_removal_sensitivity.csv",
)


def _json_equal(left: Any, right: Any, *, tolerance: float = 1e-12) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key], tolerance=tolerance) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(a, b, tolerance=tolerance) for a, b in zip(left, right)
        )
    return left == right


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, default=Path("results/paper/analysis"))
    parser.add_argument(
        "--actual", type=Path, default=Path("results/regenerated/evaluation_final")
    )
    args = parser.parse_args()
    errors: list[str] = []
    for filename in CSV_FILES:
        with (args.expected / filename).open(newline="", encoding="utf-8") as handle:
            expected = list(csv.reader(handle))
        with (args.actual / filename).open(newline="", encoding="utf-8") as handle:
            actual = list(csv.reader(handle))
        if expected != actual:
            errors.append(f"CSV differs: {filename}")
    for filename in ("batch_validation.json", "report.json"):
        expected = json.loads((args.expected / filename).read_text(encoding="utf-8"))
        actual = json.loads((args.actual / filename).read_text(encoding="utf-8"))
        if not _json_equal(expected, actual):
            errors.append(f"JSON differs beyond numeric tolerance: {filename}")
    if (args.expected / "report.md").read_text() != (args.actual / "report.md").read_text():
        errors.append("Markdown differs: report.md")
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print("[PASS] regenerated analysis matches all packaged tables and reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
