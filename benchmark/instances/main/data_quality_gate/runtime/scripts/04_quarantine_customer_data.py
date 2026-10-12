#!/usr/bin/env python3
"""Copy rejected customer data into a filesystem-backed quarantine zone."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    metadata = json.loads((artifacts / "ingested_data_object.json").read_text(encoding="utf-8"))
    quarantine = args.workspace / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    destination = quarantine / "customers.csv"
    shutil.copyfile(metadata["source_uri"], destination)
    status = {
        "success": True,
        "action": "copy",
        "destination_uri": str(destination),
        "records_quarantined": metadata["record_count"],
        "reason": "Quality score below 95",
        "errors": [],
    }
    (artifacts / "quarantine_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
