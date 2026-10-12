#!/usr/bin/env python3
"""Ingest compliance policy (reference source — JSON)."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--execution-time", type=str, default=None)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    fixtures_dir = args.fixture.parent

    policy_path = fixtures_dir / fixture["inputs"]["policy"]
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    result = {
        "source": "reference",
        "policy": policy,
        "policy_id": policy["policy_id"],
        "required_cert_types": policy["required_cert_types"],
        "ingested_at": args.execution_time,
    }
    (artifacts / "ingest_reference_source_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "ingest_reference_source_status.json").write_text(
        json.dumps({"success": True, "policy_id": policy["policy_id"], "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
