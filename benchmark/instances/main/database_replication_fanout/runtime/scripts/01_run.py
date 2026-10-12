#!/usr/bin/env python3
"""Run deterministic production export and target import mocks."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--step", choices=("export", "import"), required=True)
    parser.add_argument("--database-resource", type=Path, required=True)
    parser.add_argument("--source-fixture", type=Path)
    parser.add_argument("--target-label")
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    database = json.loads(args.database_resource.read_text(encoding="utf-8"))
    if args.step == "export":
        if args.source_fixture is None:
            raise SystemExit("--source-fixture is required for export")
        snapshot = artifacts / "snapshot.csv"
        shutil.copyfile(args.source_fixture, snapshot)
        with snapshot.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        status = {"success": True, "source_database": database["target"], "rows_exported": len(rows), "errors": []}
        (artifacts / "export_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        return
    if args.target_label is None:
        raise SystemExit("--target-label is required for import")
    with (artifacts / "snapshot.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    target = args.workspace / "mock_databases"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{args.target_label}.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    reference = {"target": database["target"], "table": database["table"], "rows_imported": len(rows)}
    (artifacts / f"{args.target_label}_ref.json").write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
    status = {"success": True, "target": args.target_label, "rows_loaded": len(rows), "errors": []}
    (artifacts / f"{args.target_label}_load_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
