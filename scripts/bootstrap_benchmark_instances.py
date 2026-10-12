#!/usr/bin/env python3
"""Create source-backed benchmark instance directories from manifest rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INSTANCE_SUBDIRECTORIES = (
    "source",
    "candidates",
    "gold",
    "contracts/artifacts",
    "fixtures/inputs",
    "runtime/scripts",
    "argo",
    "validation",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, choices=("main", "validation", "extension"))
    parser.add_argument("--pipeline", action="append", required=True)
    return parser.parse_args()


def manifest_rows() -> dict[tuple[str, str], dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {(row["split"], row["pipeline_id"]): row for row in rows}


def source_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmark_id": row["benchmark_id"],
        "dataset": {
            "id": row.get("dataset_id", "zenodo_pipeline_descriptions"),
            "version": row.get("dataset_version", "v1.0.0"),
            "doi": row.get("dataset_doi", "10.5281/zenodo.20377524"),
        },
        "description": {
            "path": f"benchmark/{row['description_path']}",
            "sha256": row["description_sha256"],
        },
        "internal_spec": {
            "path": f"benchmark/{row['internal_spec_path']}",
            "sha256": row["internal_spec_sha256"],
        },
        "annotation_use": (
            "The description is public model input. The internal specification is private "
            "reviewer evidence."
        ),
    }


def bootstrap(split: str, pipeline_id: str, rows: dict[tuple[str, str], dict[str, Any]]) -> None:
    row = rows.get((split, pipeline_id))
    if row is None:
        raise ValueError(f"No manifest row for {split}:{pipeline_id}")
    instance_dir = ROOT / "benchmark" / "instances" / split / pipeline_id
    metadata_path = instance_dir / "source" / "source_metadata.yaml"
    if instance_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing instance: {instance_dir}")
    for relative_path in INSTANCE_SUBDIRECTORIES:
        (instance_dir / relative_path).mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        yaml.safe_dump(source_metadata(row), sort_keys=False, width=100), encoding="utf-8"
    )
    (instance_dir / "README.md").write_text(
        "# Bootstrap Status\n\n"
        "This directory was created from the frozen benchmark manifest. It contains no "
        "annotations, bindings, candidate labels, mock implementations, or gold data yet.\n",
        encoding="utf-8",
    )
    print(f"bootstrapped {split}:{pipeline_id}")


def main() -> None:
    args = parse_args()
    rows = manifest_rows()
    for pipeline_id in args.pipeline:
        bootstrap(args.split, pipeline_id, rows)


if __name__ == "__main__":
    main()
