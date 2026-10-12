#!/usr/bin/env python3
"""Remove the explicitly scoped temporary workspace directory."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    target = args.workspace / "tmp"
    existed = target.exists()
    if existed:
        shutil.rmtree(target)
    status = {
        "success": True,
        "targets_processed": 1,
        "targets_deleted": 1 if existed else 0,
        "missing_targets": [] if existed else [str(target)],
        "errors": [],
    }
    artifacts = args.workspace / "artifacts"
    (artifacts / "cleanup_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
