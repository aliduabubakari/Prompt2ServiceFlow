#!/usr/bin/env python3
"""Manage Extension-50 benchmark generation in batches of five.

This script prepares the source-backed benchmark workspace for Extension-50. It
does not invent hidden gold annotations; instead, it creates the manifest rows,
instance directories, batch plans, and repeatable compile/validate/report steps
around the reviewed authoring scripts that will be developed per batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1"
INSTANCE_ROOT = ROOT / "benchmark" / "instances" / "extension"
BATCH_ROOT = ROOT / "benchmark" / "instances" / "batches"
MANIFEST_PATH = ROOT / "benchmark" / "manifest.jsonl"
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
REQUIRED_INSTANCE_FILES = (
    "source/source_metadata.yaml",
    "gold/serviceflow.yaml",
    "gold/bindings.yaml",
    "gold/artifact_mappings.yaml",
    "gold/candidate_labels.yaml",
    "gold/assertions.yaml",
    "candidates/candidate_sets.yaml",
    "runtime/manifest.yaml",
)
TOPOLOGY_MAP = {
    "linear": "Linear",
    "staged": "Staged",
    "fan_out": "Fan-out",
    "fan_in": "Fan-in",
    "fan_out_fan_in": "Fan-out/Fan-in",
    "branch_gate": "Branch/Gate",
    "windowed_batch": "Windowed Batch",
}
COMPLEXITY_MAP = {
    "simple": "Simple",
    "medium": "Medium",
    "complex": "Complex",
    "very_complex": "Very complex",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source_records() -> list[dict[str, Any]]:
    manifest = SOURCE_ROOT / "manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(
            f"Missing Extension-50 source manifest: {manifest}. "
            "Run scripts/create_extension_50_sources.py first."
        )
    records = json.loads(manifest.read_text(encoding="utf-8"))
    if len(records) != 50:
        raise ValueError(f"Expected 50 Extension-50 records, found {len(records)}")
    return records


def load_manifest_rows() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return []
    return [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_manifest_rows(rows: list[dict[str, Any]]) -> None:
    MANIFEST_PATH.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def manifest_row(record: dict[str, Any]) -> dict[str, Any]:
    description_rel = Path("source") / "extension_v1" / record["description_path"]
    spec_rel = Path("source") / "extension_v1" / record["spec_path"]
    description_path = ROOT / "benchmark" / description_rel
    spec_path = ROOT / "benchmark" / spec_rel
    return {
        "annotation_status": "not_started",
        "benchmark_id": f"extension:{record['pipeline_id']}",
        "business_domain": record["domain"],
        "complexity_label": COMPLEXITY_MAP[record["complexity"]],
        "dataset_id": "prompt2serviceflow_extension_sources",
        "dataset_version": "extension_v1",
        "dataset_doi": None,
        "description_edge_count": record["edge_count"],
        "description_path": str(description_rel),
        "description_sha256": sha256(description_path),
        "description_step_count": record["step_count"],
        "execution_model": "Bounded batch",
        "extension_track": record["track"],
        "generic_objective_count": 0,
        "information_sufficiency": "high",
        "input_modalities": record["input_modalities"],
        "internal_spec_path": str(spec_rel),
        "internal_spec_sha256": sha256(spec_path),
        "number": record["global_number"],
        "output_modalities": record["output_modalities"],
        "pipeline_id": record["pipeline_id"],
        "pipeline_name": record["name"],
        "review_status": "not_started",
        "source_edge_count": record["edge_count"],
        "source_family": record["source_family"],
        "source_repo": "prompt2serviceflow-extension-v1",
        "source_step_count": record["step_count"],
        "source_type": record["source_type"],
        "split": "extension",
        "steps_without_explicit_io_estimate": 0,
        "topology": TOPOLOGY_MAP[record["topology"]],
        "topology_key": record["topology"],
        "unknown_mechanism_count": 0,
    }


def ensure_manifest() -> None:
    source_records = load_source_records()
    extension_rows = [manifest_row(record) for record in source_records]
    non_extension_rows = [
        row for row in load_manifest_rows() if row.get("split") != "extension"
    ]
    write_manifest_rows([*non_extension_rows, *extension_rows])
    print(f"manifest extension rows written: {len(extension_rows)}")


def source_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmark_id": row["benchmark_id"],
        "dataset": {
            "id": row.get("dataset_id", "prompt2serviceflow_extension_sources"),
            "version": row.get("dataset_version", "extension_v1"),
            "doi": row.get("dataset_doi"),
        },
        "description": {
            "path": f"benchmark/{row['description_path']}",
            "sha256": row["description_sha256"],
        },
        "internal_spec": {
            "path": f"benchmark/{row['internal_spec_path']}",
            "sha256": row["internal_spec_sha256"],
        },
        "extension": {
            "track": row["extension_track"],
            "topology": row["topology_key"],
            "complexity": row["complexity_label"],
            "input_modalities": row["input_modalities"],
            "output_modalities": row["output_modalities"],
        },
        "annotation_use": (
            "The description is public model input. The companion source specification "
            "is reviewer evidence for gold annotation, not model-visible gold."
        ),
    }


def selected_records(batch: int | None, pipeline: list[str] | None) -> list[dict[str, Any]]:
    records = load_source_records()
    if batch is not None:
        records = [record for record in records if record["batch"] == batch]
    if pipeline:
        requested = set(pipeline)
        records = [
            record
            for record in records
            if record["pipeline_id"] in requested
            or f"extension:{record['pipeline_id']}" in requested
        ]
        missing = sorted(
            requested
            - {record["pipeline_id"] for record in records}
            - {f"extension:{record['pipeline_id']}" for record in records}
        )
        if missing:
            raise ValueError(f"Unknown extension pipeline(s): {missing}")
    if not records:
        raise ValueError("No Extension-50 records selected")
    return records


def bootstrap(batch: int | None, pipeline: list[str] | None, force: bool) -> None:
    ensure_manifest()
    rows = {row["pipeline_id"]: row for row in load_manifest_rows() if row.get("split") == "extension"}
    for record in selected_records(batch, pipeline):
        row = rows[record["pipeline_id"]]
        instance_dir = INSTANCE_ROOT / record["pipeline_id"]
        metadata_path = instance_dir / "source" / "source_metadata.yaml"
        if instance_dir.exists() and not force:
            print(f"skip existing extension instance: {record['pipeline_id']}")
            continue
        for relative_path in INSTANCE_SUBDIRECTORIES:
            (instance_dir / relative_path).mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            yaml.safe_dump(source_metadata(row), sort_keys=False, width=100),
            encoding="utf-8",
        )
        (instance_dir / "README.md").write_text(
            f"# {record['name']}\n\n"
            "Extension-50 benchmark instance workspace.\n\n"
            "- Source package: `benchmark/source/extension_v1`\n"
            f"- Extension track: `{record['track']}`\n"
            f"- Batch: `{record['batch']:02d}`\n"
            "- Status: source bootstrapped; gold annotations are pending.\n",
            encoding="utf-8",
        )
        print(f"bootstrapped extension:{record['pipeline_id']}")


def batch_markdown(records: list[dict[str, Any]]) -> str:
    batch = records[0]["batch"]
    author_script = f"scripts/author_extension_batch_{batch:02d}.py"
    lines = [
        f"# Extension-50 Batch {batch:02d}",
        "",
        "This batch is processed as a complete benchmark-generation unit: source review, catalogue-gap decisions, ServiceFlowIR, gold bindings, candidate labels, artifact mappings, fixtures, mock scripts, Argo output, G0-G6 validation, semantic hardening, and independent adjudication notes.",
        "",
        "## Pipelines",
        "",
        "| # | Pipeline | Track | Domain | Topology | Complexity | Steps |",
        "|---:|---|---|---|---|---|---:|",
    ]
    for record in records:
        lines.append(
            f"| {record['global_number']} | `{record['pipeline_id']}` | `{record['track']}` | "
            f"{record['domain']} | `{record['topology']}` | `{record['complexity']}` | {record['step_count']} |"
        )
    lines.extend(
        [
            "",
            "## Batch Commands",
            "",
            "```bash",
            f"python3 scripts/run_extension_benchmark.py --batch {batch} --phase bootstrap",
            f"python3 {author_script}",
            f"python3 scripts/run_extension_benchmark.py --batch {batch} --phase compile",
            f"python3 scripts/run_extension_benchmark.py --batch {batch} --phase validate",
            f"python3 scripts/run_extension_benchmark.py --batch {batch} --phase report",
            "```",
            "",
            "## Required Authoring Outputs Per Pipeline",
            "",
            "- `gold/serviceflow.yaml` with complete source-step accounting.",
            "- `gold/bindings.yaml` and `gold/artifact_mappings.yaml` compact projections.",
            "- `candidates/candidate_sets.yaml` and private `gold/candidate_labels.yaml`.",
            "- `contracts/artifacts/*.schema.json` where JSON artifacts need explicit contracts.",
            "- `fixtures/inputs/*` with credential-free deterministic inputs.",
            "- `runtime/scripts/*.py` with one task-specific mock per service intent.",
            "- `runtime/manifest.yaml` matching the ServiceFlowIR control-flow graph.",
            "- `gold/assertions.yaml` with at least one nominal G6 assertion and any branch-specific assertions.",
            "- generated `argo/workflow.yaml`, `argo/workflow_bundle.yaml`, and optional CronWorkflow resources.",
            "- `validation/report.json` with G0-G6 pass.",
            "",
            "## Semantic Hardening Checklist",
            "",
            "- Verify no Frozen-60 files were modified.",
            "- Verify every source step is accounted for as `service`, `orchestration`, `noop`, or `unresolvable`.",
            "- Prefer specific service descriptors; add a versioned catalog extension only when the existing catalogue cannot represent the source contract.",
            "- Keep event/checkpoint/window cases bounded batch; do not claim true streaming semantics.",
            "- Candidate sets must contain one gold service plus 2-5 meaningful distractors.",
            "- Run compile and G0-G6 validation before moving to the next batch.",
            "",
        ]
    )
    return "\n".join(lines)


def write_plan(batch: int | None, pipeline: list[str] | None) -> None:
    records = selected_records(batch, pipeline)
    batches = sorted(set(record["batch"] for record in records))
    for batch_number in batches:
        batch_records = [record for record in records if record["batch"] == batch_number]
        plan_path = BATCH_ROOT / f"extension_batch_{batch_number:02d}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(batch_markdown(batch_records), encoding="utf-8")
        print(f"wrote {plan_path.relative_to(ROOT)}")


def run_python(script: Path, *args: str) -> None:
    command = [sys.executable, str(script), *args]
    completed = subprocess.run(command, cwd=ROOT, text=True, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def author(batch: int) -> None:
    script = ROOT / "scripts" / f"author_extension_batch_{batch:02d}.py"
    if not script.exists():
        raise FileNotFoundError(
            f"Missing {script.relative_to(ROOT)}. Create this reviewed authoring script "
            "from the batch plan before running the author phase."
        )
    run_python(script)


def compile_instances(batch: int | None, pipeline: list[str] | None) -> None:
    for record in selected_records(batch, pipeline):
        instance_dir = INSTANCE_ROOT / record["pipeline_id"]
        if not (instance_dir / "runtime" / "manifest.yaml").exists():
            raise FileNotFoundError(
                f"{record['pipeline_id']}: missing runtime/manifest.yaml; run the batch authoring script first"
            )
        run_python(ROOT / "scripts" / "compile_instance.py", str(instance_dir))


def validate_instances(batch: int | None, pipeline: list[str] | None) -> None:
    for record in selected_records(batch, pipeline):
        instance_dir = INSTANCE_ROOT / record["pipeline_id"]
        run_python(ROOT / "scripts" / "validate_instance.py", str(instance_dir))


def report(batch: int | None, pipeline: list[str] | None) -> None:
    records = selected_records(batch, pipeline)
    rows = []
    for record in records:
        instance_dir = INSTANCE_ROOT / record["pipeline_id"]
        missing = [
            path for path in REQUIRED_INSTANCE_FILES if not (instance_dir / path).exists()
        ]
        validation_path = instance_dir / "validation" / "report.json"
        validation_status = "missing"
        if validation_path.exists():
            document = json.loads(validation_path.read_text(encoding="utf-8"))
            validation_status = document["overall_status"]
        rows.append(
            {
                "pipeline_id": record["pipeline_id"],
                "batch": record["batch"],
                "track": record["track"],
                "missing_required_files": missing,
                "validation_status": validation_status,
            }
        )

    report_root = ROOT / "benchmark" / "reports" / "extension_v1"
    report_root.mkdir(parents=True, exist_ok=True)
    suffix = f"batch_{batch:02d}" if batch else "selected"
    path = report_root / f"{suffix}_status.json"
    summary = {
        "pipeline_count": len(rows),
        "missing_file_count": sum(len(row["missing_required_files"]) for row in rows),
        "validation_status_counts": dict(Counter(row["validation_status"] for row in rows)),
        "rows": rows,
    }
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")


def status() -> None:
    records = load_source_records()
    rows = load_manifest_rows()
    extension_manifest_count = sum(1 for row in rows if row.get("split") == "extension")
    instance_count = sum(1 for record in records if (INSTANCE_ROOT / record["pipeline_id"]).is_dir())
    validation_reports = [
        INSTANCE_ROOT / record["pipeline_id"] / "validation" / "report.json"
        for record in records
    ]
    validation_statuses = []
    for path in validation_reports:
        if path.exists():
            validation_statuses.append(json.loads(path.read_text(encoding="utf-8"))["overall_status"])
        else:
            validation_statuses.append("missing")
    print(
        json.dumps(
            {
                "source_records": len(records),
                "manifest_extension_rows": extension_manifest_count,
                "instance_directories": instance_count,
                "track_counts": dict(Counter(record["track"] for record in records)),
                "validation_status_counts": dict(Counter(validation_statuses)),
            },
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, choices=range(1, 11))
    parser.add_argument("--pipeline", action="append")
    parser.add_argument(
        "--phase",
        required=True,
        choices=("manifest", "bootstrap", "plan", "author", "compile", "validate", "report", "status", "batch"),
    )
    parser.add_argument("--force", action="store_true", help="Overwrite source metadata during bootstrap.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.phase == "manifest":
        ensure_manifest()
    elif args.phase == "bootstrap":
        bootstrap(args.batch, args.pipeline, args.force)
    elif args.phase == "plan":
        write_plan(args.batch, args.pipeline)
    elif args.phase == "author":
        if args.batch is None:
            raise ValueError("--phase author requires --batch")
        author(args.batch)
    elif args.phase == "compile":
        compile_instances(args.batch, args.pipeline)
    elif args.phase == "validate":
        validate_instances(args.batch, args.pipeline)
    elif args.phase == "report":
        report(args.batch, args.pipeline)
    elif args.phase == "status":
        status()
    elif args.phase == "batch":
        if args.batch is None:
            raise ValueError("--phase batch requires --batch")
        bootstrap(args.batch, args.pipeline, args.force)
        write_plan(args.batch, args.pipeline)
        author(args.batch)
        compile_instances(args.batch, args.pipeline)
        validate_instances(args.batch, args.pipeline)
        report(args.batch, args.pipeline)


if __name__ == "__main__":
    main()
