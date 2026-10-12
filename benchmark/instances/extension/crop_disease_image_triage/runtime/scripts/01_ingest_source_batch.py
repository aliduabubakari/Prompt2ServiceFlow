#!/usr/bin/env python3
"""Ingest crop image metadata, farmer master data, and disease risk policy."""
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

    images = json.loads((fixtures_dir / fixture["inputs"]["images"]).read_text(encoding="utf-8"))
    farmers = {}
    with (fixtures_dir / fixture["inputs"]["master"]).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            farmers[row["farmer_id"]] = row
    policy = json.loads((fixtures_dir / fixture["inputs"]["policy"]).read_text(encoding="utf-8"))

    result = {
        "images": images, "farmers": farmers, "policy": policy,
        "total_images": len(images), "total_farmers": len(farmers),
        "ingested_at": args.execution_time,
    }
    (artifacts / "ingest_source_batch_artifact.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (artifacts / "ingest_source_batch_status.json").write_text(
        json.dumps({"success": True, "images": len(images), "farmers": len(farmers), "errors": []}, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
