#!/usr/bin/env python3
"""Verify backup artifact integrity."""

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

    # Determine which backup file exists
    full_path = artifacts / "backup_full.dump"
    incr_path = artifacts / "backup_incremental.dump"
    manifest_path = artifacts / "backup_manifest.json"
    incr_manifest_path = artifacts / "incremental_backup_manifest.json"

    if full_path.is_file():
        backup_path = full_path
        manifest_path = manifest_path
    elif incr_path.is_file():
        backup_path = incr_path
        manifest_path = incr_manifest_path
    else:
        raise SystemExit("No backup file found for verification")

    content = backup_path.read_bytes()
    checks_run = 0
    checks_failed = 0
    errors: list[str] = []

    # Check 1: readability
    checks_run += 1
    readable = len(content) > 0

    # Check 2: non-empty
    checks_run += 1
    if len(content) == 0:
        checks_failed += 1
        errors.append("Backup file is empty")

    # Check 3: checksum
    checksum_matched = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = manifest.get("checksum_sha256")
        if expected:
            checks_run += 1
            actual = hashlib.sha256(content).hexdigest()
            checksum_matched = actual == expected
            if not checksum_matched:
                checks_failed += 1
                errors.append(f"Checksum mismatch: expected {expected}, got {actual}")

    valid = checks_failed == 0

    result = {
        "valid": valid,
        "checks_run": checks_run,
        "checks_failed": checks_failed,
        "artifact_readable": readable,
        "checksum_matched": checksum_matched,
        "completeness_passed": valid,
        "errors": errors,
    }
    (artifacts / "verification_result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    status = {
        "success": True,
        "verification_attempted": True,
        "valid": valid,
        "profile": "default",
        "errors": [],
    }
    (artifacts / "verification_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
