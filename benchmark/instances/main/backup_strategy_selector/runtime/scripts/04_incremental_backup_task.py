#!/usr/bin/env python3
"""Mock incremental database backup creation."""

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
    backup_path = artifacts / "backup_incremental.dump"
    content = b"MOCK_INCREMENTAL_BACKUP_CONTENT__backup_strategy_selector\n" * 50
    backup_path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()

    manifest = {
        "backup_mode": "incremental",
        "database_engine": "postgresql",
        "output_uri": str(backup_path),
        "artifact_created": True,
        "checksum_sha256": checksum,
        "size_bytes": len(content),
        "checkpoint_reference": "cp-2024-01-07",
    }
    (artifacts / "incremental_backup_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    status = {
        "success": True,
        "backup_mode": "incremental",
        "backup_attempted": True,
        "output_uri": str(backup_path),
        "bytes_written": len(content),
        "errors": [],
    }
    (artifacts / "incremental_backup_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
