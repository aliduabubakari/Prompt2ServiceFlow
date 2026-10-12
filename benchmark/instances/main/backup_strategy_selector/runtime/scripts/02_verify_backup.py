#!/usr/bin/env python3
"""Verify the branch-selected mock database backup artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    backup_path = artifacts / "backup_file.dump"
    manifest = json.loads((artifacts / "backup_manifest.json").read_text(encoding="utf-8"))
    payload = backup_path.read_bytes()
    checksum_matched = hashlib.sha256(payload).hexdigest() == manifest["checksum_sha256"]
    valid = bool(payload) and checksum_matched
    result = {
        "valid": valid,
        "checks_run": 3,
        "checks_failed": 0 if valid else 1,
        "artifact_readable": True,
        "checksum_matched": checksum_matched,
        "completeness_passed": bool(payload),
        "errors": [] if valid else ["backup integrity check failed"],
    }
    (artifacts / "verification_result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "verification_status.json").write_text(
        json.dumps(
            {
                "success": valid,
                "verification_attempted": True,
                "valid": valid,
                "profile": "checksum_and_non_empty",
                "errors": result["errors"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
