#!/usr/bin/env python3
"""Ingest supplier master data (secondary source — CSV table)."""
from __future__ import annotations
import argparse, csv, json
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

    master_path = fixtures_dir / fixture["inputs"]["master"]
    suppliers = []
    with master_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            suppliers.append(row)

    result = {
        "source": "secondary",
        "suppliers": suppliers,
        "total_suppliers": len(suppliers),
        "supplier_ids": sorted(s["supplier_id"] for s in suppliers),
        "ingested_at": args.execution_time,
    }
    (artifacts / "ingest_secondary_source_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "ingest_secondary_source_status.json").write_text(
        json.dumps({"success": True, "suppliers_loaded": len(suppliers), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
