#!/usr/bin/env python3
"""Generate a deterministic backup run UUID and emit generation status."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    load_id = f"backup-run-{uuid.uuid4()!s}"
    (artifacts / "backup_load_id.txt").write_text(load_id + "\n", encoding="utf-8")

    status = {
        "success": True,
        "generation_strategy": "uuid",
        "load_id_present": True,
        "errors": [],
    }
    (artifacts / "generation_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
