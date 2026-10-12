#!/usr/bin/env python3
"""Deterministic Airflow metadata cleanup mock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TABLES = {
    "cleanup_dag_run": "dag_run",
    "cleanup_task_instance": "task_instance",
    "cleanup_log": "log",
    "cleanup_xcom": "xcom",
    "cleanup_sla_miss": "sla_miss",
    "cleanup_dag_model": "dag",
    "cleanup_task_reschedule": "task_reschedule",
    "cleanup_task_fail": "task_fail",
    "cleanup_rendered_task_instance_fields": "rendered_task_instance_fields",
    "cleanup_import_error": "import_error",
    "cleanup_base_job": "job",
    "cleanup_sessions": "session",
}


def write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--step", required=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    if args.step == "config":
        retention = {
            "max_age_days": 30,
            "cutoff_date": "2026-01-01",
            "delete_enabled": True,
        }
        write_json(artifacts / "retention_config.json", retention)
        write_json(
            artifacts / "config_status.json",
            {"success": True, "errors": [], "source": "default"},
        )
        return

    if args.step in TABLES:
        table = TABLES[args.step]
        suffix = args.step.removeprefix("cleanup_")
        write_json(
            artifacts / f"{suffix}_result.json",
            {"table": table, "deleted_rows": len(table), "cutoff_date": "2026-01-01"},
        )
        write_json(
            artifacts / f"{suffix}_status.json",
            {"success": True, "errors": [], "table": table},
        )
        return

    if args.step == "analyze":
        write_json(
            artifacts / "analyze_status.json",
            {
                "success": True,
                "errors": [],
                "analyzed_table_count": len(TABLES),
                "tables": list(TABLES.values()),
            },
        )


if __name__ == "__main__":
    main()
