#!/usr/bin/env python3
"""Deterministic DWH L2 workflow orchestration mock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def boolean(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


def write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--l2-ready", type=boolean, default=True)
    parser.add_argument("--run-label", default="batch-001")
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    if args.step == "wait_l2":
        write_json(
            artifacts / "l2_decision.json",
            {"ready": args.l2_ready, "success": True, "row_count": int(args.l2_ready)},
        )
        write_json(
            artifacts / "l2_status.json",
            {"success": True, "errors": [], "query_executed": True},
        )
        (artifacts / "l2_ready.txt").write_text(
            str(args.l2_ready).lower(), encoding="utf-8"
        )
    elif args.step == "load_id":
        load_id = f"wf-l2-{args.run_label}"
        (artifacts / "load_id.txt").write_text(load_id + "\n", encoding="utf-8")
        write_json(
            artifacts / "gen_status.json",
            {"success": True, "errors": [], "load_id": load_id},
        )
    elif args.step == "register":
        write_json(
            artifacts / "session_ref.json",
            {"load_id": "wf-l2-batch-001", "operation": "register"},
        )
        write_json(
            artifacts / "reg_status.json",
            {"success": True, "errors": [], "operation": "register"},
        )
    elif args.step == "wait_success":
        write_json(
            artifacts / "success_decision.json",
            {"completed": True, "succeeded": True, "external_step_id": "end"},
        )
    elif args.step in {"kill", "dataprep", "segment"}:
        workflow_id = {
            "kill": "sys_kill_all_session_pg",
            "dataprep": "wf_data_preparation_for_reports",
            "segment": "l1_to_l2_p_load_data_ds_client_segmentation_full",
        }[args.step]
        prefix = {"kill": "kill", "dataprep": "dataprep", "segment": "segment"}[
            args.step
        ]
        write_json(
            artifacts / f"{prefix}_result.json",
            {"workflow_id": workflow_id, "run_id": f"{workflow_id}-001"},
        )
        write_json(
            artifacts / f"{prefix}_status.json",
            {"success": True, "errors": [], "waited_for_completion": True},
        )
    elif args.step == "flag":
        write_json(
            artifacts / "sap_request_summary.json",
            {"endpoint": "/dwh/load-complete", "method": "POST", "row_count": 2},
        )
        write_json(
            artifacts / "flag_status.json",
            {"success": True, "errors": [], "http_status": 202},
        )
    elif args.step == "end":
        write_json(
            artifacts / "final_session_ref.json",
            {"load_id": "wf-l2-batch-001", "operation": "finalize"},
        )
        write_json(
            artifacts / "end_status.json",
            {"success": True, "errors": [], "operation": "finalize"},
        )


if __name__ == "__main__":
    main()
