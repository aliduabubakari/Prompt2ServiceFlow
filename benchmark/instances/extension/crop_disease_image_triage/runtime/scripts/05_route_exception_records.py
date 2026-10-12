#!/usr/bin/env python3
"""Route exception (high-risk/low-quality) records: escalate for expert agronomist review."""
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
    exceptions = evaluated["exceptions"]

    result = {"route": "exception", "records": exceptions, "total_escalated": len(exceptions),
              "action": "escalate_to_expert", "notification": "Expert agronomist review required"}
    (artifacts / "route_exception_records_artifact.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (artifacts / "route_exception_records_status.json").write_text(
        json.dumps({"success": True, "escalated": len(exceptions), "errors": []}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
