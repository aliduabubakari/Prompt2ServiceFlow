#!/usr/bin/env python3
"""Create the branch-selected mock database backup artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--database-resource", type=Path, required=True)
    parser.add_argument("--mode", choices=("full", "incremental"), required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    database = json.loads(args.database_resource.read_text(encoding="utf-8"))
    payload = f"mock-{args.mode}-backup:{database.get('database', 'backup_target_db')}\n".encode()
    payload *= 32
    backup_path = artifacts / "backup_file.dump"
    backup_path.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    manifest = {
        "backup_mode": args.mode,
        "database_engine": database.get("engine", "postgresql"),
        "output_uri": str(backup_path),
        "artifact_created": True,
        "checksum_sha256": checksum,
        "size_bytes": len(payload),
        "checkpoint_reference": "mock-checkpoint-2024-01-07" if args.mode == "incremental" else None,
    }
    (artifacts / "backup_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "backup_mode": args.mode,
        "backup_attempted": True,
        "output_uri": str(backup_path),
        "bytes_written": len(payload),
        "errors": [],
    }
    (artifacts / "backup_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
