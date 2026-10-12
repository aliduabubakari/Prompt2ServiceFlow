#!/usr/bin/env python3
"""Determine backup strategy from execution date fixture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

FULL_BACKUP_DAYS = {5}  # Saturday in python_monday_0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--execution-date", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    exec_date_str = args.execution_date.read_text(encoding="utf-8").strip()
    exec_date = datetime.strptime(exec_date_str, "%Y-%m-%d").date()
    dow = exec_date.weekday()  # Monday=0, ..., Saturday=5, Sunday=6
    is_full = dow in FULL_BACKUP_DAYS
    strategy = "full" if is_full else "incremental"
    reason = (
        f"Day of week {dow!r} {'is' if is_full else 'is not'} in full-backup days {FULL_BACKUP_DAYS!r}"
    )

    decision = {
        "selected_strategy": strategy,
        "branch_label": strategy,
        "day_of_week": dow,
        "matched_full_backup_day": is_full,
        "reason": reason,
    }
    (artifacts / "backup_strategy_decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "backup_strategy.txt").write_text(strategy, encoding="utf-8")


if __name__ == "__main__":
    main()
