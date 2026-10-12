"""Regression tests for unconditional, paired, and pass@k aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.aggregate_results import _run_row, _summarize, aggregate, to_markdown


def test_unconditional_denominator_retains_parse_failures() -> None:
    rows = [
        {
            "method": "m3",
            "status": "completed",
            "node_f1": 1.0,
            "edge_f1": 1.0,
            "wiring_f1": 1.0,
            "binding": 1.0,
            "binding_version": 1.0,
            "full_pass": True,
            "gate_statuses": {
                gate: "pass" for gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec")
            },
            "tokens": 10,
            "cost_usd": None,
            "first_failing_gate": None,
        },
        {
            "method": "m3",
            "status": "parse_error",
            "gate_statuses": {},
            "tokens": 5,
            "cost_usd": None,
            "first_failing_gate": "G0",
        },
    ]
    e1, _ = _summarize(rows)
    assert e1[0]["node_f1"] == 0.5
    assert e1[0]["node_f1_conditional"] == 1.0
    assert e1[0]["binding_top1"] == 0.5
    assert e1[0]["full_pass_rate"] == 0.5


def test_efficiency_metrics_include_token_components_and_latency() -> None:
    rows = [
        {
            "method": "m0",
            "status": "completed",
            "node_f1": 0.0,
            "edge_f1": 0.0,
            "gate_statuses": {},
            "tokens": 120,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "reasoning_tokens": 5,
            "llm_calls": 2,
            "latency_s": 3.5,
            "validator_calls": 0,
            "evaluation_validator_calls": 0,
            "cost_usd": 0.01,
            "first_failing_gate": "G0",
        }
    ]
    e1, _ = _summarize(rows)
    assert e1[0]["total_prompt_tokens"] == 100
    assert e1[0]["total_completion_tokens"] == 20
    assert e1[0]["total_reasoning_tokens"] == 5
    assert e1[0]["mean_llm_calls"] == 2
    assert e1[0]["p95_latency_s"] == 3.5


def test_length_finish_reason_is_reported_as_truncation() -> None:
    manifest = _manifest("model-a", 0, False)
    manifest["usage"]["per_stage"] = [
        {"stage": "m3_ir", "finish_reason": "length"},
        {"stage": "m4_repair_1", "finish_reason": "stop"},
    ]
    row = _run_row(manifest)
    e1, _ = _summarize([row])
    assert row["length_truncated_calls"] == 1
    assert e1[0]["length_truncated_calls"] == 1
    assert e1[0]["length_truncated_runs"] == 1
    assert e1[0]["length_truncated_run_rate"] == 1.0


def test_unscored_and_empty_wiring_runs_do_not_enter_wiring_denominator() -> None:
    rows = [
        {
            "method": "m3",
            "status": "parse_error",
            "wiring_applicable": None,
            "gate_statuses": {},
            "tokens": 10,
            "cost_usd": None,
            "first_failing_gate": "G0",
        },
        {
            "method": "m3",
            "status": "completed",
            "wiring_applicable": False,
            "wiring_f1": None,
            "gate_statuses": {},
            "tokens": 10,
            "cost_usd": None,
            "first_failing_gate": None,
        },
    ]
    e1, _ = _summarize(rows)
    assert e1[0]["wiring_f1"] is None
    assert e1[0]["wiring_applicable_runs"] == 0


def _manifest(model: str, sample: int, passed: bool) -> dict:
    return {
        "run_id": f"run-{model}-{sample}",
        "sample_index": sample,
        "method_status": "completed",
        "method": {"id": "m3"},
        "model": {"model_id": model},
        "instance": {"id": "demo", "split": "main"},
        "usage": {"total_tokens": 10, "cost_usd": None},
        "evaluation": {
            "validation": {"gate_statuses": {}},
            "score_summary": {
                "full_pass_g0_g6": passed,
                "first_failing_gate": None if passed else "G6-Exec",
                "node_f1": 1.0,
                "edge_f1": 1.0,
                "wiring_f1": 1.0,
                "binding_top1_accuracy": 1.0,
            },
        },
    }


def test_pass_at_k_keeps_models_as_separate_paired_units(tmp_path: Path) -> None:
    runs = []
    outcomes = {"model-a": [True, False, False], "model-b": [False, False, False]}
    for model, values in outcomes.items():
        for sample, passed in enumerate(values):
            run_dir = tmp_path / f"{model}-{sample}"
            run_dir.mkdir()
            manifest_path = run_dir / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest(model, sample, passed)))
            runs.append({"manifest_path": str(manifest_path)})
    batch = tmp_path / "batch.json"
    batch.write_text(
        json.dumps(
            {
                "status": "complete",
                "expected_cell_count": 6,
                "runs": runs,
            }
        )
    )
    report = aggregate(tmp_path, batch_summary=batch, benchmark_root=tmp_path / "benchmark")
    pass_rates = {
        item["k"]: item["pass_at_k"] for item in report["pass_at_k"] if item["method"] == "m3"
    }
    assert pass_rates[1] == pytest.approx(1 / 6)
    assert pass_rates[3] == pytest.approx(1 / 2)


def test_incomplete_batch_is_rejected(tmp_path: Path) -> None:
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"status": "running", "runs": []}))
    with pytest.raises(ValueError, match="not complete"):
        aggregate(tmp_path, batch_summary=batch, benchmark_root=tmp_path / "benchmark")


def test_invalid_observation_is_reported_but_excluded_from_semantic_means(
    tmp_path: Path,
) -> None:
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    valid_manifest = _manifest("model-a", 0, True)
    valid_path = valid_dir / "manifest.json"
    valid_path.write_text(json.dumps(valid_manifest))

    invalid_dir = tmp_path / "invalid"
    invalid_dir.mkdir()
    invalid_manifest = _manifest("model-a", 0, False)
    invalid_manifest.update(
        {
            "run_id": "invalid-m5",
            "method": {"id": "m5"},
            "run_validity": "invalid",
            "failure_category": "provider_prompt_template_incompatibility",
            "failure_message": "conversation roles must alternate",
            "evaluation": {"status": "empty_submission"},
        }
    )
    invalid_path = invalid_dir / "manifest.json"
    invalid_path.write_text(json.dumps(invalid_manifest))

    batch = tmp_path / "batch.json"
    batch.write_text(
        json.dumps(
            {
                "status": "complete_with_invalid_observations",
                "expected_cell_count": 2,
                "expected_cells": [
                    {
                        "model": "model-a",
                        "method": "m3",
                        "split": "main",
                        "instance": "demo",
                        "sample_index": 0,
                    },
                    {
                        "model": "model-a",
                        "method": "m5",
                        "split": "main",
                        "instance": "demo",
                        "sample_index": 0,
                    },
                ],
                "runs": [
                    {
                        "status": "recorded",
                        "manifest_path": str(valid_path),
                        "model": "model-a",
                        "method": "m3",
                        "split": "main",
                        "instance": "demo",
                        "sample_index": 0,
                    },
                    {
                        "status": "recorded_invalid",
                        "manifest_path": str(invalid_path),
                        "model": "model-a",
                        "method": "m5",
                        "split": "main",
                        "instance": "demo",
                        "sample_index": 0,
                    },
                ],
            }
        )
    )

    report = aggregate(tmp_path, batch_summary=batch, benchmark_root=tmp_path / "benchmark")
    assert report["declared_run_count"] == 2
    assert report["run_count"] == 1
    assert report["invalid_observation_count"] == 1
    assert report["e1"][0]["method"] == "m3"
    assert report["invalid_observations"][0]["failure_category"] == (
        "provider_prompt_template_incompatibility"
    )
    m5_coverage = next(row for row in report["operational_coverage"] if row["method"] == "m5")
    assert m5_coverage["coverage_rate"] == 0.0
    markdown = to_markdown(report)
    assert "Operational coverage and compatibility" in markdown
    assert "Invalid observations count as non-passes" in markdown
