"""Prepare the immutable benchmark source layer and reconcile companion specs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ZENODO_RECORD = {
    "record_id": 20377524,
    "doi": "10.5281/zenodo.20377524",
    "title": (
        "Structured ETL and Data-Preparation Pipeline Descriptions "
        "for LLM Workflow Generation Studies"
    ),
    "version": "v1.0.0",
    "publication_date": "2026-05-25",
    "license": "CC-BY-4.0",
    "archive_name": "zenodo_pipeline_descriptions_descriptions_only.zip",
    "archive_size_bytes": 83820,
    "archive_checksum": "md5:3ed544ae7995e810247d130cf9dd2a76",
}

REQUIRED_SOURCE_PATHS = (
    "README.md",
    "manifest.csv",
    "inventories/main_40_pipeline_inventory.csv",
    "inventories/validation_20_pipeline_inventory.csv",
    "main_40",
    "validation_20",
)

STEP_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)
EDGE_RE = re.compile(r"^\s*-\s+([A-Za-z0-9_.-]+)\s+->\s+([A-Za-z0-9_.-]+)\s*$", re.MULTILINE)
GENERIC_OBJECTIVE = "implement this operation as a task in the workflow"
UNKNOWN_MECHANISM_RE = re.compile(r"^\s*-\s+Mechanism:\s+unknown\s*$", re.MULTILINE | re.IGNORECASE)
INPUT_RE = re.compile(r"^\s*-\s+Inputs:\s+(.+?)\s*$", re.MULTILINE)
OUTPUT_RE = re.compile(r"^\s*-\s+Outputs:\s+(.+?)\s*$", re.MULTILINE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.iterdir()):
        target = destination / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)


def replace_managed_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def index_specs(spec_root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    index: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(spec_root.glob("*.json")):
        data = read_json(path)
        pipeline_id = str(data.get("pipeline_id", "")).strip()
        if not pipeline_id:
            raise ValueError(f"Missing pipeline_id in {path}")
        if pipeline_id in index:
            raise ValueError(f"Duplicate pipeline_id {pipeline_id!r} in {path} and {index[pipeline_id][0]}")
        index[pipeline_id] = (path, data)
    return index


def normalize_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def concrete_edge_count(spec: dict[str, Any]) -> int:
    """Count real directed edges, excluding legacy terminal edges to null."""
    edges = spec.get("control_flow", {}).get("edges", [])
    return sum(bool(edge.get("from") and edge.get("to")) for edge in edges)


def description_metrics(text: str) -> dict[str, int | str]:
    step_count = len(STEP_RE.findall(text))
    edge_count = len(EDGE_RE.findall(text))
    generic_count = text.lower().count(GENERIC_OBJECTIVE)
    unknown_count = len(UNKNOWN_MECHANISM_RE.findall(text))
    inputs_count = len(INPUT_RE.findall(text))
    outputs_count = len(OUTPUT_RE.findall(text))
    steps_without_explicit_io = max(step_count - max(inputs_count, outputs_count), 0)

    if generic_count:
        sufficiency = "low"
    elif unknown_count or steps_without_explicit_io >= max(1, step_count // 2):
        sufficiency = "medium"
    else:
        sufficiency = "high"

    return {
        "description_step_count": step_count,
        "description_edge_count": edge_count,
        "generic_objective_count": generic_count,
        "unknown_mechanism_count": unknown_count,
        "steps_without_explicit_io_estimate": steps_without_explicit_io,
        "information_sufficiency": sufficiency,
    }


def iter_files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def write_checksums(root: Path) -> None:
    checksum_path = root / "checksums.sha256"
    lines = []
    for path in iter_files(root):
        if path == checksum_path:
            continue
        lines.append(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_public_source(source_root: Path, snapshot_root: Path) -> None:
    replace_managed_directory(snapshot_root)
    (snapshot_root / "descriptions").mkdir()
    shutil.copytree(source_root / "main_40", snapshot_root / "descriptions" / "main_40")
    shutil.copytree(source_root / "validation_20", snapshot_root / "descriptions" / "validation_20")
    shutil.copytree(source_root / "inventories", snapshot_root / "inventories")
    shutil.copy2(source_root / "manifest.csv", snapshot_root / "manifest.csv")
    shutil.copy2(source_root / "README.md", snapshot_root / "UPSTREAM_README.md")

    source_metadata = {
        **ZENODO_RECORD,
        "snapshot_created_at": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(source_root.resolve()),
        "source_directory_name": source_root.name,
        "archive_present_locally": (source_root.parent / ZENODO_RECORD["archive_name"]).exists(),
        "snapshot_policy": "immutable copy; do not edit files under this directory",
    }
    write_json(snapshot_root / "SOURCE.json", source_metadata)
    write_checksums(snapshot_root)


def copy_internal_specs(spec_source: Path, destination: Path) -> dict[str, dict[str, Any]]:
    replace_managed_directory(destination)
    copied: dict[str, dict[str, Any]] = {}

    for split, source_subdir in (
        ("main", spec_source / "main_40" / "specs"),
        ("validation", spec_source / "validation_20" / "specs"),
    ):
        target_subdir = destination / f"{split}_40" if split == "main" else destination / "validation_20"
        target_subdir.mkdir()
        for source_path in sorted(source_subdir.glob("*.json")):
            data = read_json(source_path)
            pipeline_id = str(data["pipeline_id"])
            target_path = target_subdir / source_path.name
            shutil.copy2(source_path, target_path)
            copied[f"{split}:{pipeline_id}"] = {
                "source_path": source_path,
                "target_path": target_path,
                "data": data,
            }

    provenance = f"""# Internal Companion Specifications

Generated on {date.today().isoformat()} from:

`{spec_source.resolve()}`

These JSON files are companion annotation evidence copied from the earlier
`spec-matters` workspace. They are not part of the description-only Zenodo
archive and must not be supplied to evaluated models unless a separately named
structured-input track explicitly uses them.

The source fingerprints, quality warnings, and original metadata are retained.
Gold bindings and benchmark labels will be stored elsewhere.
"""
    (destination / "PROVENANCE.md").write_text(provenance, encoding="utf-8")
    write_checksums(destination)
    return copied


def reconcile(
    source_root: Path,
    snapshot_root: Path,
    internal_specs_root: Path,
    benchmark_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_rows = load_manifest(source_root / "manifest.csv")
    spec_indexes = {
        "main": index_specs(internal_specs_root / "main_40"),
        "validation": index_specs(internal_specs_root / "validation_20"),
    }

    normalized_rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for row in manifest_rows:
        split = row["split"]
        pipeline_id = row["pipeline_id"]
        description_source = source_root / row["description_path"]
        description_snapshot = (
            snapshot_root / "descriptions" / split.replace("validation", "validation_20")
        )
        if split == "main":
            description_snapshot = snapshot_root / "descriptions" / "main_40" / description_source.name
        else:
            description_snapshot = (
                snapshot_root / "descriptions" / "validation_20" / description_source.name
            )

        spec_entry = spec_indexes.get(split, {}).get(pipeline_id)
        if not spec_entry:
            issues.append(
                {
                    "severity": "error",
                    "pipeline_id": pipeline_id,
                    "message": f"No {split} companion spec resolves to this pipeline ID.",
                }
            )
            continue

        spec_path, spec = spec_entry
        text = description_source.read_text(encoding="utf-8")
        metrics = description_metrics(text)
        spec_step_count = len(spec.get("steps", []))
        spec_edge_count = concrete_edge_count(spec)

        if metrics["description_step_count"] != spec_step_count:
            issues.append(
                {
                    "severity": "error",
                    "pipeline_id": pipeline_id,
                    "message": (
                        "Step-count mismatch: description="
                        f"{metrics['description_step_count']}, spec={spec_step_count}."
                    ),
                }
            )
        if metrics["description_edge_count"] != spec_edge_count:
            issues.append(
                {
                    "severity": "error",
                    "pipeline_id": pipeline_id,
                    "message": (
                        "Edge-count mismatch: description="
                        f"{metrics['description_edge_count']}, spec={spec_edge_count}."
                    ),
                }
            )
        if normalize_name(row.get("pipeline_name")) != normalize_name(spec.get("pipeline_name")):
            issues.append(
                {
                    "severity": "warning",
                    "pipeline_id": pipeline_id,
                    "message": (
                        f"Pipeline-name difference: manifest={row.get('pipeline_name')!r}, "
                        f"spec={spec.get('pipeline_name')!r}."
                    ),
                }
            )

        internal_relative = spec_path.relative_to(internal_specs_root)
        normalized_rows.append(
            {
                "benchmark_id": f"{split}:{pipeline_id}",
                "split": split,
                "number": int(row["number"]),
                "pipeline_id": pipeline_id,
                "pipeline_name": row["pipeline_name"],
                "source_type": row["source_type"],
                "source_family": row["source_family"],
                "source_repo": row["source_repo"],
                "business_domain": row["business_domain"],
                "execution_model": row["execution_model"],
                "topology": row["topology"],
                "complexity_label": row["complexity_label"],
                "description_path": description_snapshot.relative_to(benchmark_root).as_posix(),
                "description_sha256": sha256_file(description_snapshot),
                "internal_spec_path": (
                    Path("source") / "internal_specs" / internal_relative
                ).as_posix(),
                "internal_spec_sha256": sha256_file(spec_path),
                "source_step_count": spec_step_count,
                "source_edge_count": spec_edge_count,
                "annotation_status": "not_started",
                "review_status": "not_started",
                **metrics,
            }
        )

    expected_ids = {(row["split"], row["pipeline_id"]) for row in manifest_rows}
    indexed_ids = {
        (split, pipeline_id)
        for split, index in spec_indexes.items()
        for pipeline_id in index
    }
    for split, pipeline_id in sorted(indexed_ids - expected_ids):
        issues.append(
            {
                "severity": "error",
                "pipeline_id": pipeline_id,
                "message": f"Unreferenced {split} companion spec.",
            }
        )

    normalized_rows.sort(key=lambda item: (item["split"] != "main", item["number"]))
    counts = Counter(row["information_sufficiency"] for row in normalized_rows)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_rows": len(manifest_rows),
        "normalized_rows": len(normalized_rows),
        "main_rows": sum(row["split"] == "main" for row in normalized_rows),
        "validation_rows": sum(row["split"] == "validation" for row in normalized_rows),
        "information_sufficiency": dict(sorted(counts.items())),
        "errors": sum(issue["severity"] == "error" for issue in issues),
        "warnings": sum(issue["severity"] == "warning" for issue in issues),
        "issues": issues,
    }
    return normalized_rows, report


def write_manifest(benchmark_root: Path, rows: list[dict[str, Any]]) -> None:
    manifest_path = benchmark_root / "manifest.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    split_dir = benchmark_root / "splits"
    split_dir.mkdir(exist_ok=True)
    development = [row["benchmark_id"] for row in rows if row["split"] == "main"]
    validation = [row["benchmark_id"] for row in rows if row["split"] == "validation"]
    ambiguity = [
        row["benchmark_id"] for row in rows if row["information_sufficiency"] == "low"
    ]
    write_json(split_dir / "development.json", {"benchmark_ids": development})
    write_json(split_dir / "validation.json", {"benchmark_ids": validation})
    write_json(split_dir / "ambiguity_track.json", {"benchmark_ids": ambiguity})


def validate_source_locations(source_root: Path, spec_source: Path) -> None:
    missing = [str(source_root / rel) for rel in REQUIRED_SOURCE_PATHS if not (source_root / rel).exists()]
    for path in (
        spec_source / "main_40" / "specs",
        spec_source / "validation_20" / "specs",
    ):
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing required source paths:\n- " + "\n- ".join(missing))


def prepare_sources(project_root: Path, source_root: Path, spec_source: Path) -> dict[str, Any]:
    validate_source_locations(source_root, spec_source)
    benchmark_root = project_root / "benchmark"
    snapshot_root = benchmark_root / "source" / "zenodo_v1_0_0"
    internal_specs_root = benchmark_root / "source" / "internal_specs"

    copy_public_source(source_root, snapshot_root)
    copy_internal_specs(spec_source, internal_specs_root)
    rows, report = reconcile(source_root, snapshot_root, internal_specs_root, benchmark_root)
    write_manifest(benchmark_root, rows)

    reports_root = benchmark_root / "reports"
    reports_root.mkdir(exist_ok=True)
    write_json(reports_root / "source_reconciliation.json", report)
    write_json(
        reports_root / "information_sufficiency.json",
        {
            "generated_at": report["generated_at"],
            "counts": report["information_sufficiency"],
            "instances": [
                {
                    "benchmark_id": row["benchmark_id"],
                    "information_sufficiency": row["information_sufficiency"],
                    "generic_objective_count": row["generic_objective_count"],
                    "unknown_mechanism_count": row["unknown_mechanism_count"],
                    "steps_without_explicit_io_estimate": row[
                        "steps_without_explicit_io_estimate"
                    ],
                }
                for row in rows
            ],
        },
    )
    return report


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument(
        "--zenodo-source",
        type=Path,
        default=project_root / "zenodo_pipeline_descriptions_descriptions_only",
    )
    parser.add_argument(
        "--spec-source",
        type=Path,
        default=Path(
            os.environ.get(
                "P2SF_SPEC_SOURCE",
                project_root / "benchmark" / "source" / "internal_specs",
            )
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = prepare_sources(
        args.project_root.resolve(),
        args.zenodo_source.resolve(),
        args.spec_source.resolve(),
    )
    print(
        "Prepared benchmark source layer: "
        f"{report['normalized_rows']} instances, "
        f"{report['errors']} errors, {report['warnings']} warnings."
    )
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
