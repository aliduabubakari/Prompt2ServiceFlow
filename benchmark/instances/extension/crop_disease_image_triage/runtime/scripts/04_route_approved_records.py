#!/usr/bin/env python3
"""Route approved (low-risk) records: prepare for automated processing."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace; artifacts = root / "artifacts"

    evaluated = json.loads((artifacts / "evaluate_policy_or_risk_artifact.json").read_text(encoding="utf-8"))
    approved = evaluated["approved"]

    result = {"route": "approved", "records": approved, "total_routed": len(approved),
              "action": "auto_process", "notification": "No expert review required"}
    (artifacts / "route_approved_records_artifact.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (artifacts / "route_approved_records_status.json").write_text(
        json.dumps({"success": True, "routed": len(approved), "errors": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
