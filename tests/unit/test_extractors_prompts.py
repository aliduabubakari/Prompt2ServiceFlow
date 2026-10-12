"""Unit tests for output extractors and visible-view prompt builders."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.experiments import prompts
from prompt2serviceflow.experiments.extractors import (
    extract_multi_file,
    extract_service_references,
    extract_yaml_document,
)
from prompt2serviceflow.experiments.workspace import build_workspace


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark"
INSTANCE = BENCHMARK / "instances" / "main" / "airflow_db_cleanup"


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("ws")
    build_workspace(INSTANCE, out, split="main", benchmark_root=BENCHMARK)
    return out / "main" / INSTANCE.name


def test_extract_yaml_from_fence() -> None:
    text = "Here you go:\n```yaml\na: 1\nb: [x, y]\n```\n"
    document, error = extract_yaml_document(text)
    assert error is None
    assert document == {"a": 1, "b": ["x", "y"]}


def test_extract_yaml_raw() -> None:
    document, error = extract_yaml_document("a: 1\n")
    assert error is None and document == {"a": 1}


@pytest.mark.parametrize(
    "marker",
    ["===FILE: serviceflow.yaml===", "===FILE: serviceflow.yaml"],
)
def test_extract_yaml_normalizes_single_serviceflow_marker(marker: str) -> None:
    document, error = extract_yaml_document(f"{marker}\na: 1\n")
    assert error is None and document == {"a": 1}


def test_extract_yaml_invalid() -> None:
    _, error = extract_yaml_document("a: [unclosed\n")
    assert error is not None


def test_extract_multi_file() -> None:
    text = (
        "===FILE: runtime/manifest.yaml===\n```yaml\ntasks: []\n```\n\n"
        "===FILE: scripts/01_run.py===\nprint('hi')\n"
    )
    files, error = extract_multi_file(text)
    assert error is None
    assert files["runtime/manifest.yaml"] == "tasks: []"
    assert files["scripts/01_run.py"] == "print('hi')"


def test_extract_multi_file_strips_python_fence() -> None:
    text = (
        "===FILE: runtime/manifest.yaml===\n```yaml\ntasks: []\n```\n\n"
        "===FILE: runtime/scripts/01_run.py===\n"
        "```python\n#!/usr/bin/env python3\nprint('hi')\n```\n"
    )
    files, error = extract_multi_file(text)
    assert error is None
    assert files["runtime/scripts/01_run.py"] == (
        "#!/usr/bin/env python3\nprint('hi')"
    )


def test_extract_multi_file_rejects_unsafe_paths() -> None:
    _, error = extract_multi_file("===FILE: ../evil.py===\nx\n")
    assert error is not None and "unsafe" in error


def test_extract_service_references_fail_closed() -> None:
    catalog = {"alpha_service", "beta_service"}
    found = extract_service_references(
        "uses alpha_service and gamma_service twice: gamma_service", catalog | {"gamma_service"}
    )
    assert set(found["referenced_service_ids"]) == {"alpha_service", "gamma_service"}
    assert extract_service_references("nothing here", catalog)["reference_count"] == 0
    # substring of a longer identifier must not match
    assert extract_service_references("alpha_service_v2", catalog)["reference_count"] == 0


def test_visible_view_scopes(workspace: Path) -> None:
    m0_view = prompts.build_visible_view(workspace, "m0")
    assert set(m0_view) == {"task"}
    m3_view = prompts.build_visible_view(workspace, "m3")
    assert {
        "task",
        "candidates",
        "catalog",
        "serviceflow_schema",
        "runtime_manifest_schema",
        "fixtures",
    } <= set(m3_view)


def test_prompts_contain_no_private_content(workspace: Path) -> None:
    view = prompts.build_visible_view(workspace, "m3")
    manifest = prompts.load_workspace_manifest(workspace)
    _, user = prompts.m3_ir_prompts(view, manifest)
    # Gold/private vocabulary must never appear in method-visible prompts.
    assert "required_service_id" not in user
    assert "internal_spec" not in user
    assert "source_refs" not in user
    # Gold intent ids are snake-cased derivatives; only the public
    # source-step refs (camel-cased) may appear.
    assert "cleanup_dag_run" not in user
    assert "cleanup_DagRun" in user  # public source_step_ref
    # Public content is present.
    assert "airflow_metadata_retention_cleaner" in user
    assert manifest["catalog"]["sanitized_catalog_yaml_sha256"] in user


def test_catalog_payload_full_descriptors_only_for_candidates(workspace: Path) -> None:
    payload = prompts.load_catalog_payload(workspace)
    candidates = yaml.safe_load((workspace / "candidates" / "candidate_sets.yaml").read_text())
    candidate_ids = {
        service_id
        for candidate_set in candidates["candidate_sets"]
        for service_id in candidate_set["service_ids"]
    }
    assert "airflow_metadata_retention_cleaner" in candidate_ids
    # Candidate services appear with full descriptor sections.
    assert payload.count("interface:") >= len(candidate_ids) - 1
    # Non-candidate services appear only as index lines.
    assert "## Remaining catalog services (index only)" in payload


def test_m2_prompt_includes_catalog_and_candidates(workspace: Path) -> None:
    view = prompts.build_visible_view(workspace, "m2")
    _, user = prompts.m2_prompts(view)
    assert "# Service catalog" in user
    assert "# Service candidate sets" in user
    assert "# Available artifact contract schemas" in user
    assert view["contracts"] in user


def test_m3_prompt_declares_ir_only_deterministic_projection(workspace: Path) -> None:
    view = prompts.build_visible_view(workspace, "m3")
    manifest = prompts.load_workspace_manifest(workspace)
    system, ir_user = prompts.m3_ir_prompts(view, manifest)
    assert "quote string scalars containing a colon" in system
    assert "one ServiceFlowIR JSON object" in ir_user
    assert "Output one valid JSON object only" in ir_user

    assert "deterministically derives" in ir_user
    assert "do not emit runtime files" in ir_user


def test_m4_g0_repair_prompt_uses_minimal_context(workspace: Path) -> None:
    view = prompts.build_visible_view(workspace, "m4")
    _, user = prompts.m4_repair_prompts(
        view,
        {
            "serviceflow.yaml": "bad: value",
        },
        {
            "first_failing_gate": "G0",
            "gates": [
                {
                    "gate": "G0",
                    "status": "fail",
                    "description": "schema",
                    "diagnostics": [{"code": "G0_SCHEMA_ERROR", "message": "bad type"}],
                }
            ],
        },
    )
    assert view["serviceflow_schema"] in user
    assert view["contracts"] not in user
    assert view["candidates"] not in user
    assert view["catalog"] not in user
    assert "one COMPLETE corrected ServiceFlowIR" in user
    assert "valid JSON object only" in user


def test_m4_binding_repair_retains_grounding_context(workspace: Path) -> None:
    view = prompts.build_visible_view(workspace, "m4")
    _, user = prompts.m4_repair_prompts(
        view,
        {"serviceflow.yaml": "ir_version: 0.1.0"},
        {
            "first_failing_gate": "G3",
            "gates": [
                {
                    "gate": "G3",
                    "status": "fail",
                    "description": "binding",
                    "diagnostics": [{"code": "G3_PORT", "message": "bad port"}],
                }
            ],
        },
    )
    assert view["candidates"] in user
    assert view["catalog"] in user
    assert view["contracts"] in user


def test_contract_ablation_redacts_all_structured_diagnostics(workspace: Path) -> None:
    view = prompts.build_visible_view(
        workspace,
        "m4",
        ablation={
            "withhold_contracts": True,
            "strip_contract_details": True,
            "diagnostic_visibility": "gate_identity",
        },
    )
    _, user = prompts.m4_repair_prompts(
        view,
        {"serviceflow.yaml": "ir_version: 0.1.0"},
        {
            "first_failing_gate": "G3",
            "gates": [
                {
                    "gate": "G3",
                    "status": "fail",
                    "description": "binding compatibility",
                    "diagnostics": [
                        {
                            "code": "G3_SCHEMA_MISMATCH",
                            "message": "secret contract detail",
                        }
                    ],
                }
            ],
        },
    )
    assert "secret contract detail" not in user
    assert "G3_SCHEMA_MISMATCH" not in user
    assert "no structured diagnostic codes or paths" in user
    assert "artifact contracts withheld" in user


def test_g5_feedback_ablation_redacts_only_g5_diagnostics(workspace: Path) -> None:
    view = prompts.build_visible_view(
        workspace,
        "m4",
        ablation={"redact_diagnostic_gates": ["G5"]},
    )
    _, user = prompts.m4_repair_prompts(
        view,
        {"serviceflow.yaml": "ir_version: 0.1.0"},
        {
            "first_failing_gate": "G3",
            "gates": [
                {
                    "gate": "G3",
                    "status": "fail",
                    "description": "binding compatibility",
                    "diagnostics": [{"code": "G3_VISIBLE", "message": "keep me"}],
                },
                {
                    "gate": "G5",
                    "status": "fail",
                    "description": "projection",
                    "diagnostics": [{"code": "G5_SECRET", "message": "hide me"}],
                },
            ],
        },
    )
    assert "G3_VISIBLE" in user
    assert "keep me" in user
    assert "G5_SECRET" not in user
    assert "hide me" not in user
    assert "## G5 (projection)" in user
    assert "no structured diagnostic codes or paths" in user


def test_m4_repair_prompt_carries_prior_diagnostics_and_marks_cycles(workspace: Path) -> None:
    view = prompts.build_visible_view(workspace, "m4")
    prior = {
        "first_failing_gate": "G1",
        "gates": [
            {
                "gate": "G1",
                "status": "fail",
                "description": "artifact consistency",
                "diagnostics": [{"code": "G1_OLD", "message": "preserve the producer"}],
            }
        ],
    }
    current = {
        "first_failing_gate": "G3",
        "gates": [
            {
                "gate": "G3",
                "status": "fail",
                "description": "binding",
                "diagnostics": [{"code": "G3_ACTIVE", "message": "fix the input port"}],
            }
        ],
    }
    _, user = prompts.m4_repair_prompts(
        view,
        {"serviceflow.yaml": "ir_version: 0.1.0"},
        current,
        diagnostic_history=[prior, current, current],
    )
    assert "G1_OLD" in user
    assert "PRIOR—DO NOT REINTRODUCE" in user
    assert "G3_ACTIVE" in user
    assert "Repeated validator state detected: yes" in user


def test_contract_ablation_removes_contract_evidence(workspace: Path) -> None:
    view = prompts.build_visible_view(
        workspace,
        "m4",
        ablation={"withhold_contracts": True, "strip_contract_details": True},
    )
    assert view["contracts"].startswith("(artifact contracts withheld")
    assert "contracts:" not in view["catalog"]
    assert "schema_ref:" not in view["catalog"]


@pytest.mark.parametrize(
    ("profile", "present", "absent"),
    [
        ("name_description", "capability:", "interface:"),
        ("artifacts", "outputs:", "parameters:"),
        ("parameters", "parameters:", "policies:"),
        ("policies", "policies:", "invocation:"),
        ("full", "invocation:", "__not_a_real_descriptor_field__"),
    ],
)
def test_descriptor_ablation_profiles(
    workspace: Path, profile: str, present: str, absent: str
) -> None:
    payload = prompts.load_catalog_payload(workspace, descriptor_profile=profile)
    assert present in payload
    assert absent not in payload
