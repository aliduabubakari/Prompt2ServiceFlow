from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from prompt2serviceflow.experiments.prompts import ABLATION_PROTOCOL_VERSION


ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "experiments/config/freeze.deepinfra.ablation.v24.json"
RUNNER = ROOT / "scripts/run_ablation_experiment.py"


def _runner_module():
    spec = importlib.util.spec_from_file_location("run_ablation_experiment", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v24_confirmatory_conditions_match_runner_defaults() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    runner = _runner_module()

    assert freeze["ablation_protocol_version"] == ABLATION_PROTOCOL_VERSION
    assert freeze["ablation"]["confirmatory_conditions"] == list(
        runner.CONFIRMATORY_ABLATIONS
    )
    assert "a4_no_serviceflow_ir_stage" not in runner.CONFIRMATORY_ABLATIONS
    assert freeze["design"]["cell_count"] == 110 * 5 * 3


def test_stage_removal_is_separate_and_has_no_end_to_end_claim() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    sensitivity = freeze["ablation"]["stage_removal_sensitivity"]

    assert sensitivity["status"] == "separate_nonconfirmatory_analysis"
    assert "end-to-end full pass" in sensitivity["not_comparable"]
    original_source = ROOT / sensitivity["source_batch"]
    packaged_source = ROOT / "results/paper/batch_summaries/primary-qwen480-v21.json"
    assert original_source.is_file() or packaged_source.is_file()


def test_resume_accepts_only_missing_legacy_retrieval_metadata() -> None:
    runner = _runner_module()
    expected = {
        "freeze_id": "freeze-v24",
        "model": "qwen",
        "retrieval_configuration": {"top_k": 5},
    }

    assert runner._resume_design_mismatches(
        {"freeze_id": "freeze-v24", "model": "qwen"}, expected
    ) == []
    assert runner._resume_design_mismatches(
        {
            "freeze_id": "freeze-v24",
            "model": "qwen",
            "retrieval_configuration": {"top_k": 10},
        },
        expected,
    ) == [
        "retrieval_configuration: batch={'top_k': 10}, requested={'top_k': 5}"
    ]
    assert runner._resume_design_mismatches(
        {"freeze_id": "different-freeze", "model": "qwen"}, expected
    ) == ["freeze_id: batch='different-freeze', requested='freeze-v24'"]
