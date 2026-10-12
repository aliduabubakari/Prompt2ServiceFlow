"""Tests for the submission-workspace builder and the leakage scanner."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.experiments.leakage import (
    iter_instance_workspaces,
    scan_workspace,
    scan_workspace_root,
)
from prompt2serviceflow.experiments.workspace import (
    WorkspaceBuildError,
    build_workspace,
    build_workspaces,
)


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark"
MAIN = BENCHMARK / "instances" / "main"
VALIDATION = BENCHMARK / "instances" / "validation"

EXPECTED_TOP_LEVEL = {
    "task.md",
    "candidates",
    "catalog",
    "schemas",
    "contracts",
    "fixtures",
    "bin",
    "submission",
    "workspace.yaml",
}


def _build(instance_dir: Path, tmp_path: Path, split: str) -> Path:
    build_workspace(instance_dir, tmp_path, split=split, benchmark_root=BENCHMARK)
    return tmp_path / split / instance_dir.name


def test_build_main_instance_layout(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    assert {child.name for child in workspace.iterdir()} == EXPECTED_TOP_LEVEL
    assert (workspace / "submission").is_dir()
    assert not any((workspace / "submission").iterdir())
    assert (workspace / "task.md").is_file()
    assert (workspace / "candidates" / "candidate_sets.yaml").is_file()
    assert (workspace / "catalog" / "catalog.yaml").is_file()
    assert (workspace / "catalog" / "services").is_dir()
    assert (workspace / "schemas" / "serviceflow_ir.schema.json").is_file()


def test_workspace_contains_no_private_paths(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    relative = {
        path.relative_to(workspace).as_posix() for path in workspace.rglob("*") if path.is_file()
    }
    # Directory components that must never appear (whole-component match, so
    # legitimate names like ``reviewed_python_udf_transformer.yaml`` or
    # ``runtime_manifest.schema.json`` do not false-positive).
    forbidden_components = {"gold", "runtime", "argo", "review", "reviews", "source"}
    forbidden_name_fragments = ("candidate_labels", "assertions", "bindings", "artifact_mappings")
    for path in relative:
        *directories, filename = path.split("/")
        assert not (set(directories) & forbidden_components), f"private path leaked: {path}"
        for fragment in forbidden_name_fragments:
            assert fragment not in filename, f"private file leaked into workspace: {path}"


def test_catalog_is_sanitized(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    index = yaml.safe_load((workspace / "catalog" / "catalog.yaml").read_text())
    assert "generation" not in index
    descriptors = list((workspace / "catalog" / "services").glob("*.yaml"))
    assert descriptors, "expected descriptors in workspace catalog"
    for descriptor_path in descriptors:
        document = yaml.safe_load(descriptor_path.read_text())
        assert "provenance" not in document, f"provenance leaked in {descriptor_path.name}"
        assert "service_id" in document and "interface" in document


def test_workspace_schemas_are_sanitized(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    import json

    descriptor_schema = json.loads(
        (workspace / "schemas" / "service_descriptor.schema.json").read_text()
    )
    assert "provenance" not in descriptor_schema["properties"]
    assert "provenance" not in descriptor_schema["required"]
    ir_schema = json.loads((workspace / "schemas" / "serviceflow_ir.schema.json").read_text())
    source_properties = ir_schema["properties"]["source"]["properties"]
    assert "internal_spec_path" not in source_properties
    assert "internal_spec_sha256" not in source_properties
    evidence_enum = ir_schema["$defs"]["evidence"]["properties"]["source"]["enum"]
    assert evidence_enum == ["description"]


def test_catalog_pin_matches_authored_snapshot(tmp_path: Path) -> None:
    instance_dir = MAIN / "airflow_db_cleanup"
    workspace = _build(instance_dir, tmp_path, "main")
    gold = yaml.safe_load((instance_dir / "gold" / "serviceflow.yaml").read_text())
    manifest = yaml.safe_load((workspace / "workspace.yaml").read_text())
    assert manifest["catalog"]["version"] == gold["catalog_snapshot"]["version"]
    candidate = yaml.safe_load((workspace / "candidates" / "candidate_sets.yaml").read_text())
    assert candidate["catalog_snapshot"]["version"] == gold["catalog_snapshot"]["version"]


def test_expectation_fixture_manifest_is_excluded(tmp_path: Path) -> None:
    workspace = _build(MAIN / "fraud_detection_triage", tmp_path, "main")
    assert not (workspace / "fixtures" / "inputs" / "fixture.json").exists()
    # Data inputs remain public.
    assert (workspace / "fixtures" / "inputs" / "transactions_high_risk.csv").is_file()
    manifest = yaml.safe_load((workspace / "workspace.yaml").read_text())
    excluded = {item["path"] for item in manifest["exclusions"]}
    assert "fixtures/inputs/fixture.json" in excluded


def test_candidate_file_is_label_free_for_all_instances() -> None:
    for split_dir in (MAIN, VALIDATION):
        for candidate_path in sorted(split_dir.glob("*/candidates/candidate_sets.yaml")):
            document = yaml.safe_load(candidate_path.read_text())

            def keys(node: object) -> set[str]:
                found: set[str] = set()
                if isinstance(node, dict):
                    for key, value in node.items():
                        found.add(str(key))
                        found |= keys(value)
                elif isinstance(node, list):
                    for item in node:
                        found |= keys(item)
                return found

            assert not (keys(document) & {"labels", "required_service_id"}), candidate_path


def test_scanner_passes_on_fresh_build(tmp_path: Path) -> None:
    validation_instance = sorted(
        child for child in VALIDATION.iterdir() if child.is_dir()
    )[0]
    _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    _build(validation_instance, tmp_path, "validation")
    report = scan_workspace_root(tmp_path)
    assert report["workspaces_scanned"] == 2
    assert report["status"] == "pass", report["findings"]


def test_scanner_detects_planted_gold(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    planted = workspace / "gold" / "serviceflow.yaml"
    planted.parent.mkdir(parents=True)
    planted.write_text("ir_version: 0.1.0\n")
    findings = scan_workspace(workspace)
    kinds = {finding["kind"] for finding in findings}
    assert "forbidden_path" in kinds
    assert "manifest_integrity" in kinds  # unlisted file


def test_scanner_detects_label_content(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    candidate_path = workspace / "candidates" / "candidate_sets.yaml"
    candidate_path.write_text(candidate_path.read_text() + "\nrequired_service_id: x\n")
    findings = scan_workspace(workspace)
    kinds = {finding["kind"] for finding in findings}
    assert "forbidden_content" in kinds or "candidate_labels" in kinds


def test_scanner_detects_unsanitized_descriptor(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    descriptor = next((workspace / "catalog" / "services").glob("*.yaml"))
    descriptor.write_text(descriptor.read_text() + "\nprovenance:\n  source_refs: [main:x#y]\n")
    findings = scan_workspace(workspace)
    kinds = {finding["kind"] for finding in findings}
    assert "catalog_unsanitized" in kinds
    assert "forbidden_content" in kinds


def test_manifest_integrity_detects_tampering(tmp_path: Path) -> None:
    workspace = _build(MAIN / "airflow_db_cleanup", tmp_path, "main")
    task = workspace / "task.md"
    task.write_text(task.read_text() + "\nextra line\n")
    findings = scan_workspace(workspace)
    assert any(finding["kind"] == "manifest_integrity" for finding in findings)


def test_rebuild_requires_force(tmp_path: Path) -> None:
    instance_dir = MAIN / "airflow_db_cleanup"
    build_workspace(instance_dir, tmp_path, split="main", benchmark_root=BENCHMARK)
    with pytest.raises(WorkspaceBuildError):
        build_workspace(instance_dir, tmp_path, split="main", benchmark_root=BENCHMARK)
    build_workspace(instance_dir, tmp_path, split="main", benchmark_root=BENCHMARK, force=True)


def test_build_manifest_written(tmp_path: Path) -> None:
    manifest = build_workspaces(
        benchmark_root=BENCHMARK,
        output_root=tmp_path,
        splits=("main",),
        instance_ids=["airflow_db_cleanup", "data_quality_gate"],
    )
    assert manifest["workspace_count"] == 2
    assert (tmp_path / "_build_manifest.json").is_file()
    workspaces = list(iter_instance_workspaces(tmp_path))
    assert len(workspaces) == 2


def test_workspace_file_digests_match_manifest(tmp_path: Path) -> None:
    workspace = _build(MAIN / "daily_sales_report", tmp_path, "main")
    manifest = yaml.safe_load((workspace / "workspace.yaml").read_text())
    for entry in manifest["files"]:
        digest = hashlib.sha256((workspace / entry["path"]).read_bytes()).hexdigest()
        assert digest == entry["sha256"], entry["path"]
