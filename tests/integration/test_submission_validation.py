"""Tests for public submission validation (G0-G5 + G6-Exec) and compilation.

Test fixtures are built evaluation-side: a reference submission is derived
from an instance's gold ServiceFlowIR and runtime layer, adjusted to the
public workspace contract (internal-spec fields removed, catalog anchor set
to the sanitized workspace catalog). Methods never see gold; these tests only
use it to verify that (a) reference-quality submissions pass the public gates
and (b) specific corruptions produce specific diagnostics.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.experiments.submission import (
    compile_submission,
    validate_submission,
)
from prompt2serviceflow.experiments.workspace import build_workspace


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark"
INSTANCE = BENCHMARK / "instances" / "main" / "airflow_db_cleanup"


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    build_workspace(INSTANCE, tmp_path, split="main", benchmark_root=BENCHMARK)
    return tmp_path / "main" / INSTANCE.name


def _reference_submission(workspace: Path) -> Path:
    """Derive a reference submission from gold, on the public contract."""
    submission = workspace / "submission"
    submission.mkdir(exist_ok=True)
    serviceflow = yaml.safe_load((INSTANCE / "gold" / "serviceflow.yaml").read_text())
    # Methods never see internal-spec fields; the workspace schema forbids them.
    serviceflow["source"].pop("internal_spec_path", None)
    serviceflow["source"].pop("internal_spec_sha256", None)
    workspace_manifest = yaml.safe_load((workspace / "workspace.yaml").read_text())
    serviceflow["catalog_snapshot"] = {
        "catalog_id": "serviceflow_catalog",
        "version": workspace_manifest["catalog"]["version"],
        "sha256": workspace_manifest["catalog"]["sanitized_catalog_yaml_sha256"],
    }
    (submission / "serviceflow.yaml").write_text(
        yaml.safe_dump(serviceflow, sort_keys=False), encoding="utf-8"
    )
    runtime = submission / "runtime"
    shutil.copytree(INSTANCE / "runtime", runtime)
    for pycache in runtime.rglob("__pycache__"):
        shutil.rmtree(pycache)
    return submission


@pytest.fixture()
def submission(workspace: Path) -> Path:
    return _reference_submission(workspace)


def _codes(report: dict, gate: str) -> set[str]:
    return {
        diagnostic["code"]
        for item in report["gates"]
        if item["gate"] == gate
        for diagnostic in item["diagnostics"]
    }


def _gate(report: dict, gate: str) -> dict:
    return next(item for item in report["gates"] if item["gate"] == gate)


def _rewrite_serviceflow(submission: Path, transform) -> None:
    path = submission / "serviceflow.yaml"
    document = yaml.safe_load(path.read_text())
    transform(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_reference_submission_passes_all_gates(workspace: Path, submission: Path) -> None:
    report = validate_submission(workspace, submission)
    assert report["overall_status"] == "pass", json.dumps(report["gates"], indent=2)[:4000]
    assert report["first_failing_gate"] is None
    assert [gate["gate"] for gate in report["gates"]] == [
        "G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec",
    ]
    assert all(gate["status"] == "pass" for gate in report["gates"])


def test_report_contains_no_assertion_content(workspace: Path, submission: Path) -> None:
    report = validate_submission(workspace, submission)
    text = json.dumps(report)
    assert "assertions" not in text
    assert "expected_route" not in text
    g6 = _gate(report, "G6-Exec")
    scenario_names = {item["scenario"] for item in g6["details"]["scenarios"]}
    manifest = yaml.safe_load((submission / "runtime" / "manifest.yaml").read_text())
    assert scenario_names == {item["name"] for item in manifest["scenarios"]}


def test_no_exec_skips_g6(workspace: Path, submission: Path) -> None:
    report = validate_submission(workspace, submission, run_execution=False)
    assert _gate(report, "G6-Exec")["status"] == "skipped"
    assert report["overall_status"] == "pass"


def test_empty_submission_fails_g0_and_skips_dependents(workspace: Path) -> None:
    empty = workspace / "submission"
    report = validate_submission(workspace, empty)
    assert report["overall_status"] == "fail"
    assert report["first_failing_gate"] == "G0"
    assert "G0_MISSING_FILE" in _codes(report, "G0")
    for gate in ("G1", "G2", "G3", "G4", "G5", "G6-Exec"):
        assert _gate(report, gate)["status"] == "skipped", gate


def test_schema_error_g0(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        del document["service_intents"]

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G0_SCHEMA_ERROR" in _codes(report, "G0")
    # Downstream gates skip rather than crash on a schema-invalid document.
    for gate in ("G1", "G2", "G3", "G4"):
        assert _gate(report, gate)["status"] == "skipped", gate
    assert report["first_failing_gate"] == "G0"


def test_script_syntax_error_g0(workspace: Path, submission: Path) -> None:
    script = submission / "runtime" / "scripts" / "01_run.py"
    script.write_text("def broken(:\n", encoding="utf-8")
    report = validate_submission(workspace, submission)
    assert "G0_SCRIPT_SYNTAX" in _codes(report, "G0")


def test_unknown_service_g2(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        document["bindings"][0]["service_id"] = "nonexistent_service_xyz"

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G2_UNRESOLVED_SERVICE" in _codes(report, "G2")


def test_catalog_version_mismatch_g2(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        document["catalog_snapshot"]["version"] = "0.0.0"

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G2_CATALOG_VERSION_MISMATCH" in _codes(report, "G2")


def test_missing_required_parameter_g3(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        binding = document["bindings"][0]
        binding["parameter_bindings"] = {}

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G3_REQUIRED_PARAMETER_UNBOUND" in _codes(report, "G3")


def test_input_type_mismatch_g3(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        # Corrupt the data_type of one artifact consumed by a bound input,
        # using a schema-legal but wrong value (schema-invalid values are
        # correctly rejected earlier at G0).
        binding = document["bindings"][0]
        artifact_id = binding["input_bindings"][0]["artifact_id"]
        for artifact in document["artifacts"]:
            if artifact["artifact_id"] == artifact_id:
                current = artifact["data_type"]
                artifact["data_type"] = "table" if current != "table" else "parquet"

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G3_INPUT_TYPE_MISMATCH" in _codes(report, "G3")


def test_network_policy_g4(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        # airflow_metadata_retention_cleaner requires network access; forbid it.
        for intent in document["service_intents"]:
            if intent["intent_id"] == "cleanup_dag_run":
                intent["required_policy_properties"]["network_access"] = "forbidden"

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G4_NETWORK_POLICY" in _codes(report, "G4")


def test_manifest_identity_mismatch_g1(workspace: Path, submission: Path) -> None:
    manifest_path = submission / "runtime" / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["tasks"] = manifest["tasks"][1:]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    report = validate_submission(workspace, submission)
    assert "G1_MANIFEST_IDENTITY_MISMATCH" in _codes(report, "G1")


def test_control_flow_cycle_g1(workspace: Path, submission: Path) -> None:
    def transform(document: dict) -> None:
        edges = document["control_flow"]["edges"]
        # Close a cycle back to the first intent.
        intents = [item["intent_id"] for item in document["service_intents"]]
        edges.append({"from": intents[-1], "to": intents[0]})

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert "G1_CYCLE" in _codes(report, "G1")


def test_compile_submission_writes_argo(workspace: Path, submission: Path) -> None:
    written = compile_submission(workspace, submission)
    workflow = submission / "argo" / "workflow.yaml"
    assert workflow.is_file()
    assert written["workflow"].endswith("workflow.yaml")
    document = yaml.safe_load(workflow.read_text())
    assert document["kind"] == "Workflow"


def test_compile_submission_is_deterministic(workspace: Path, submission: Path) -> None:
    compile_submission(workspace, submission, submission / "argo_a")
    compile_submission(workspace, submission, submission / "argo_b")
    files_a = sorted((submission / "argo_a").rglob("*"))
    files_b = sorted((submission / "argo_b").rglob("*"))
    assert [p.relative_to(submission / "argo_a") for p in files_a] == [
        p.relative_to(submission / "argo_b") for p in files_b
    ]
    for path_a, path_b in zip(files_a, files_b):
        if path_a.is_file():
            assert path_a.read_bytes() == path_b.read_bytes(), path_a.name


def test_schema_uri_in_artifact_ref_is_diagnostic_not_crash(
    workspace: Path, submission: Path
) -> None:
    # Models sometimes copy catalog-side schema:// URIs into artifact
    # schema_ref fields. That must produce diagnostics, never a crash.
    def transform(document: dict) -> None:
        for artifact in document["artifacts"]:
            if artifact.get("schema_ref"):
                artifact["schema_ref"] = "schema://retention_cutoff_config/v1"
                return

    _rewrite_serviceflow(submission, transform)
    report = validate_submission(workspace, submission)
    assert report["overall_status"] == "fail"
    all_codes = {
        diagnostic["code"]
        for gate in report["gates"]
        for diagnostic in gate["diagnostics"]
    }
    assert "G0_ARTIFACT_SCHEMA_MISSING" in all_codes
    assert not any(code.endswith("INTERNAL_ERROR") for code in all_codes)


def test_g6_exec_error_surfaces(workspace: Path, submission: Path) -> None:
    script = submission / "runtime" / "scripts" / "01_run.py"
    script.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    report = validate_submission(workspace, submission)
    assert "G6_EXEC_ERROR" in _codes(report, "G6-Exec")
    assert report["overall_status"] == "fail"
