#!/usr/bin/env python3
"""Export the qualified benchmark into a standalone, flat numbered repository."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = ROOT.parent / "ServiceComposeBench-ETL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    return parser.parse_args()


def load_inventory_names() -> dict[str, str]:
    path = ROOT / "benchmark_paper" / "pipeline_inventory_prompt2serviceflow_110.tex"
    names: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(M|V|E)(\d{2})\s*&\s*([^&]+?)\s*&", line)
        if not match:
            continue
        legacy_id = f"{match.group(1)}{match.group(2)}"
        name = match.group(3)
        name = name.replace(r"\allowbreak{}", "").replace(r"\-", "-")
        name = name.replace(r"\_", "_").replace("{", "").replace("}", "")
        names[legacy_id] = re.sub(r"\s+", " ", name).strip()
    if len(names) != 110:
        raise ValueError(f"expected 110 inventory names, found {len(names)}")
    return names


def provenance_group(row: dict[str, Any]) -> str:
    split = row["split"]
    if split == "main" and row.get("source_type") == "Original":
        return "frozen_repository_derived"
    if split == "main":
        return "frozen_synthetic"
    if split == "validation":
        return "frozen_validation_holdout"
    return "diversity_extension_synthetic"


def legacy_id(row: dict[str, Any]) -> str:
    prefix = {"main": "M", "validation": "V", "extension": "E"}[row["split"]]
    return f"{prefix}{int(row['number']):02d}"


def instance_by_description() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted((ROOT / "benchmark" / "instances").glob("*/*")):
        serviceflow_path = path / "gold" / "serviceflow.yaml"
        if not path.is_dir() or not serviceflow_path.is_file():
            continue
        serviceflow = yaml.safe_load(serviceflow_path.read_text(encoding="utf-8"))
        result[serviceflow["source"]["description_path"]] = path
    if len(result) != 110:
        raise ValueError(f"expected 110 instance packages, found {len(result)}")
    return result


def copy_runtime_code(destination: Path) -> None:
    package = destination / "src" / "prompt2serviceflow"
    package.mkdir(parents=True)
    shutil.copy2(ROOT / "src" / "prompt2serviceflow" / "__init__.py", package / "__init__.py")
    for component in ("compiler", "validators"):
        shutil.copytree(
            ROOT / "src" / "prompt2serviceflow" / component,
            package / component,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def main() -> None:
    args = parse_args()
    destination = args.destination.resolve()
    if destination.exists():
        raise FileExistsError(
            f"destination already exists: {destination}; choose a new path or remove it explicitly"
        )
    destination.mkdir(parents=True)

    names = load_inventory_names()
    source_instances = instance_by_description()
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 110:
        raise ValueError(f"expected 110 manifest rows, found {len(rows)}")

    benchmark_root = destination / "benchmark"
    pipelines_root = benchmark_root / "pipelines"
    pipelines_root.mkdir(parents=True)
    shutil.copytree(ROOT / "benchmark" / "catalog", benchmark_root / "catalog")
    shutil.copytree(ROOT / "benchmark" / "source", benchmark_root / "source")
    shutil.copytree(ROOT / "schemas", destination / "schemas")
    copy_runtime_code(destination)

    exported_rows = []
    for sequence, row in enumerate(rows, 1):
        old_id = legacy_id(row)
        source_instance = source_instances[row["description_path"]]
        runtime_manifest = yaml.safe_load(
            (source_instance / "runtime" / "manifest.yaml").read_text(encoding="utf-8")
        )
        runtime_pipeline_id = runtime_manifest["pipeline_id"]
        instance_id = f"SCB-ETL-{sequence:03d}"
        directory_name = f"{sequence:03d}_{runtime_pipeline_id}"
        target = pipelines_root / directory_name
        shutil.copytree(
            source_instance,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )
        metadata = {
            "benchmark": "ServiceComposeBench-ETL",
            "release_version": "1.0.0",
            "instance_id": instance_id,
            "numeric_id": sequence,
            "display_name": names[old_id],
            "runtime_pipeline_id": runtime_pipeline_id,
            "qualification": {
                "g5_static_argo": "pass",
                "g6_local_scenarios": "pass",
                "g6_argo_cluster": "pending",
            },
            "provenance": {
                "legacy_id": old_id,
                "legacy_benchmark_id": row["benchmark_id"],
                "legacy_split": row["split"],
                "group": provenance_group(row),
                "source_type": row.get("source_type"),
                "source_repository": row.get("source_repo"),
                "description_path": row["description_path"],
                "description_sha256": row["description_sha256"],
                "internal_spec_path": row["internal_spec_path"],
                "internal_spec_sha256": row["internal_spec_sha256"],
            },
        }
        (target / "benchmark_metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False, width=100), encoding="utf-8"
        )

        exported = dict(row)
        exported["legacy_annotation_status"] = exported.get("annotation_status")
        exported["legacy_review_status"] = exported.get("review_status")
        exported.update(
            {
                "collection": "ServiceComposeBench-ETL",
                "release_version": "1.0.0",
                "instance_id": instance_id,
                "numeric_id": sequence,
                "legacy_id": old_id,
                "display_name": names[old_id],
                "runtime_pipeline_id": runtime_pipeline_id,
                "directory": f"pipelines/{directory_name}",
                "provenance_group": provenance_group(row),
                "annotation_status": "qualified",
                "review_status": "independent_review_pending",
                "qualification": "G5+G6-local",
            }
        )
        exported_rows.append(exported)

    (benchmark_root / "manifest.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in exported_rows),
        encoding="utf-8",
    )
    (benchmark_root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    print(f"exported {len(exported_rows)} pipelines to {destination}")


if __name__ == "__main__":
    main()
