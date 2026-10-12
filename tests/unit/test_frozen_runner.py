"""Regression tests for frozen-runner invalid-observation handling."""

from __future__ import annotations

import json
from pathlib import Path

from prompt2serviceflow.experiments import prompts
from prompt2serviceflow.experiments.harness import HARNESS_VERSION
from prompt2serviceflow.experiments.runtime_compiler import RUNTIME_COMPILER_VERSION
from scripts.run_frozen_experiment import (
    PRIMARY_METHODS,
    _classify_infrastructure_failure,
    _classify_invalid_m5_failure,
    _record_invalid_attempt,
    _record_invalid_m5,
    _publication_model_selection_allowed,
    _publication_methods,
    _resume_mismatches,
    _sample_seeds,
)


def test_prompt_template_failure_has_explicit_compatibility_category() -> None:
    manifest = {
        "last_assistant_error": (
            "Error rendering prompt with jinja template: conversation roles must alternate"
        )
    }
    assert _classify_invalid_m5_failure(manifest) == ("provider_prompt_template_incompatibility")


def test_primary_model_serving_failure_is_infrastructure() -> None:
    manifest = {
        "method_status": "llm_error",
        "method_error": '400: {"message":"No models loaded."}',
    }
    assert _classify_infrastructure_failure(manifest) == "model_serving_connectivity"


def test_malformed_model_output_is_not_infrastructure() -> None:
    manifest = {
        "method_status": "parse_error",
        "method_error": "ServiceFlowIR output is not a parseable YAML document",
    }
    assert _classify_infrastructure_failure(manifest) is None


def test_cloud_authentication_and_service_failures_are_infrastructure() -> None:
    assert (
        _classify_infrastructure_failure({"method_error": "401: Unauthorized"})
        == "provider_authentication"
    )
    assert (
        _classify_infrastructure_failure({"method_error": "503: Service unavailable"})
        == "provider_service_failure"
    )


def test_invalid_attempt_is_audited_without_completing_cell(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"run_id": "run-1", "method_error": "LM Link closed"}))
    summary: dict = {"runs": []}

    attempt = _record_invalid_attempt(
        summary=summary,
        run_dir=run_dir,
        cell=("model-a", "m2", "main", "demo", 0),
        category="model_serving_connectivity",
        message="LM Link closed",
    )

    assert attempt["instance"] == "demo"
    assert summary["runs"] == []
    assert len(summary["invalid_attempts"]) == 1
    persisted = json.loads(manifest_path.read_text())
    assert persisted["run_validity"] == "invalid"
    assert persisted["result_inclusion"] == "operational_coverage_only"


def test_invalid_m5_is_persisted_for_operational_coverage(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "run_validity": "invalid",
                "last_assistant_error": "No models loaded",
            }
        )
    )
    summary: dict = {}
    cell = ("model-a", "m5", "main", "demo", 0)

    record = _record_invalid_m5(
        summary=summary,
        run_dir=run_dir,
        cell=cell,
        message="provider unavailable",
    )

    assert record["status"] == "recorded_invalid"
    assert record["failure_category"] == "model_serving_connectivity"
    assert summary["invalid_observations"][0]["instance"] == "demo"
    persisted = json.loads(manifest_path.read_text())
    assert persisted["result_inclusion"] == "operational_coverage_only"
    assert persisted["failure_message"] == "provider unavailable"


def test_resume_rejects_pre_v201_protocol_summary(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"
    summary = {
        "freeze_id": "freeze-x",
        "models": ["model-a"],
        "methods": ["m5"],
        "split": "main",
        "samples_per_instance": 1,
        "instances": [{"split": "main", "id": "demo"}],
    }
    mismatches = _resume_mismatches(
        summary,
        freeze_id="freeze-x",
        model_ids=["model-a"],
        methods=("m5",),
        split="main",
        samples=1,
        selected=[("main", workspace, tmp_path / "instance")],
    )
    assert any(item.startswith("prompt_version:") for item in mismatches)
    assert any(item.startswith("m5_image_version:") for item in mismatches)


def test_primary_method_set_excludes_m5() -> None:
    assert PRIMARY_METHODS == ("m0", "m1", "m2", "m3", "m4")


def test_publication_methods_can_include_controlled_m5() -> None:
    freeze = {"compared_methods": ["m0", "m1", "m2", "m3", "m4", "m5"]}
    assert _publication_methods(freeze) == ("m0", "m1", "m2", "m3", "m4", "m5")
    assert _publication_methods({"primary_methods": list(PRIMARY_METHODS)}) == PRIMARY_METHODS


def test_sample_seeds_use_predeclared_schedule() -> None:
    freeze = {"decoding": {"sample_seeds": [101, 202, 303]}}
    assert _sample_seeds(freeze, 3, configured_seed=101) == [101, 202, 303]


def test_frozen_publication_allows_only_declared_model_blocks() -> None:
    freeze = {
        "model_roster": ["model-a", "model-b"],
        "execution": {"model_blocks": [["model-a"], ["model-b"]]},
    }
    assert _publication_model_selection_allowed(freeze, ["model-a", "model-b"])
    assert _publication_model_selection_allowed(freeze, ["model-a"])
    assert _publication_model_selection_allowed(freeze, ["model-b"])
    assert not _publication_model_selection_allowed(freeze, ["model-b", "model-a"])
    assert not _publication_model_selection_allowed(freeze, ["model-a", "unknown"])


def test_primary_resume_is_not_coupled_to_m5_image_version(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"
    summary = {
        "freeze_id": "freeze-x",
        "prompt_version": prompts.PROMPT_VERSION,
        "harness_version": HARNESS_VERSION,
        "runtime_compiler_version": RUNTIME_COMPILER_VERSION,
        "models": ["model-a"],
        "methods": list(PRIMARY_METHODS),
        "split": "main",
        "samples_per_instance": 1,
        "instances": [{"split": "main", "id": "demo"}],
    }
    mismatches = _resume_mismatches(
        summary,
        freeze_id="freeze-x",
        model_ids=["model-a"],
        methods=PRIMARY_METHODS,
        split="main",
        samples=1,
        selected=[("main", workspace, tmp_path / "instance")],
    )
    assert not any(item.startswith("m5_image_version:") for item in mismatches)
