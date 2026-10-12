#!/usr/bin/env python3
"""Deterministic PCD extraction and processing mock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SENSOR_STEPS = {"check_pcd_sftp_folder", "check_pcd_shared_folder"}
FINAL_STEPS = {"pcd_file_upload", "etl_notification"}


def boolean(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


def write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--available", type=boolean, default=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    step = args.step

    if step in SENSOR_STEPS:
        write_json(
            artifacts / f"{step}_decision.json",
            {"available": args.available, "success": True},
        )
        write_json(
            artifacts / f"{step}_status.json",
            {"success": True, "errors": [], "checked": True},
        )
        if step == "check_pcd_shared_folder":
            (artifacts / "pcd_data_available.txt").write_text(
                str(args.available).lower(), encoding="utf-8"
            )
    elif step == "pcd_file_upload":
        write_json(
            artifacts / "pcd_file_upload_result.json",
            {"job_name": "pcd-file-upload-001", "namespace": "pcd"},
        )
        write_json(
            artifacts / "pcd_file_upload_status.json",
            {"success": True, "errors": [], "condition": "Complete"},
        )
    elif step == "etl_notification":
        write_json(
            artifacts / "etl_notification_status.json",
            {"sent": True, "success": True, "recipient_count": 1},
        )
    elif step not in FINAL_STEPS:
        write_json(
            artifacts / f"{step}_result.json",
            {
                "dataset": step,
                "record_count": 2,
                "records": [{"id": 1}, {"id": 2}],
            },
        )
        write_json(
            artifacts / f"{step}_status.json",
            {"success": True, "errors": [], "http_status": 200},
        )


if __name__ == "__main__":
    main()
