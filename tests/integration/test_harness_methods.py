"""End-to-end harness tests using a scripted stub LLM (no network).

The stub is scripted evaluation-side with gold-derived artifacts, so these
tests exercise the complete path — visible-view prompts, deterministic
parsing, submission assembly, public validation, private scoring, repair
loops, and run-manifest logging — without any API access.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.experiments.harness import run_one
from prompt2serviceflow.experiments.llm import ModelConfig, StubLLMClient, UsageLedger
from prompt2serviceflow.experiments.methods import run_m4
from prompt2serviceflow.experiments.workspace import build_workspace


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark"
INSTANCE = BENCHMARK / "instances" / "main" / "airflow_db_cleanup"
MODEL = ModelConfig(model_id="stub", model_name="stub-model")


def _gold_serviceflow_yaml(workspace: Path) -> str:
    document = yaml.safe_load((INSTANCE / "gold" / "serviceflow.yaml").read_text())
    document["source"].pop("internal_spec_path", None)
    document["source"].pop("internal_spec_sha256", None)
    manifest = yaml.safe_load((workspace / "workspace.yaml").read_text())
    document["catalog_snapshot"] = {
        "catalog_id": "serviceflow_catalog",
        "version": manifest["catalog"]["version"],
        "sha256": manifest["catalog"]["sanitized_catalog_yaml_sha256"],
    }
    return yaml.safe_dump(document, sort_keys=False)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    build_workspace(INSTANCE, tmp_path / "ws", split="main", benchmark_root=BENCHMARK)
    return tmp_path / "ws" / "main" / INSTANCE.name


def _stub_factory(script: dict[str, str]):
    def factory(config: ModelConfig, ledger: UsageLedger) -> StubLLMClient:
        return StubLLMClient(config, ledger, script=script)

    return factory


def test_m0_direct_argo_pipeline(workspace: Path, tmp_path: Path) -> None:
    argo_yaml = (
        "apiVersion: argoproj.io/v1alpha1\nkind: Workflow\n"
        "metadata: {generateName: cleanup-}\n"
        "spec:\n  templates:\n  - name: airflow_metadata_retention_cleaner\n"
        "    container: {image: python:3.12-slim}\n"
    )
    manifest = run_one(
        "m0",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        client_factory=_stub_factory({"m0_argo": argo_yaml}),
    )
    run_dir = Path(manifest["run_id"]) if Path(manifest["run_id"]).is_absolute() else tmp_path / "runs" / manifest["run_id"]
    assert manifest["method_status"] == "completed"
    assessment = json.loads((run_dir / "argo_assessment.json").read_text())
    assert assessment["yaml_parse"] == "pass"
    assert assessment["documents"]["has_workflow"] is True
    assert assessment["service_extraction"]["referenced_service_ids"] == [
        "airflow_metadata_retention_cleaner"
    ]
    direct = json.loads((run_dir / "direct_score.json").read_text())
    assert direct["service_grounded"] is True
    assert "airflow_metadata_retention_cleaner" in direct["correct_services"]
    assert manifest["usage"]["llm_calls"] == 1
    assert manifest["visible_input_policy"]["method_view"] == ("task.md",)


def test_m0_fenced_response_is_normalized(workspace: Path, tmp_path: Path) -> None:
    argo_yaml = (
        "apiVersion: argoproj.io/v1alpha1\nkind: Workflow\n"
        "metadata: {generateName: cleanup-}\n"
        "spec:\n  templates:\n  - name: airflow_metadata_retention_cleaner\n"
        "    container: {image: python:3.12-slim}\n"
    )
    manifest = run_one(
        "m0",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        client_factory=_stub_factory({"m0_argo": f"Sure, here is the workflow:\n```yaml\n{argo_yaml}```\n"}),
    )
    run_dir = tmp_path / "runs" / manifest["run_id"]
    assessment = json.loads((run_dir / "argo_assessment.json").read_text())
    assert assessment["yaml_parse"] == "pass"
    assert assessment["service_extraction"]["referenced_service_ids"] == [
        "airflow_metadata_retention_cleaner"
    ]


def test_m1_two_stage_pipeline(workspace: Path, tmp_path: Path) -> None:
    dag = '{"nodes": [{"id": "fetch", "description": "fetch"}, {"id": "load", "description": "load"}], "edges": [{"from": "fetch", "to": "load"}]}'
    argo = "apiVersion: argoproj.io/v1alpha1\nkind: Workflow\nmetadata: {generateName: x-}\nspec: {}\n"
    manifest = run_one(
        "m1",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        client_factory=_stub_factory({"m1_dag": dag, "m1_argo": argo}),
    )
    assert manifest["method_status"] == "completed"
    assert manifest["method_error"] is None
    assert manifest["usage"]["llm_calls"] == 2


def test_m1_parse_error_on_bad_dag(workspace: Path, tmp_path: Path) -> None:
    manifest = run_one(
        "m1",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        client_factory=_stub_factory({"m1_dag": "not json at all"}),
    )
    assert manifest["method_status"] == "parse_error"
    assert manifest["evaluation"] == {}


def test_m3_full_pipeline_scores_perfect(workspace: Path, tmp_path: Path) -> None:
    script = {
        "m3_ir": _gold_serviceflow_yaml(workspace),
    }
    manifest = run_one(
        "m3",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        client_factory=_stub_factory(script),
    )
    assert manifest["method_status"] == "completed"
    run_dir = tmp_path / "runs" / manifest["run_id"]
    assert (run_dir / "submission" / "serviceflow.yaml").is_file()
    assert (run_dir / "submission" / "runtime" / "manifest.yaml").is_file()
    assert (run_dir / "prompts" / "m3_ir.user.txt").is_file()
    assert not (run_dir / "responses" / "m3_runtime.txt").exists()
    score = json.loads((run_dir / "score.json").read_text())
    # Public execution passes through the deterministic compiler; private
    # semantic assertions remain independent and may reject generic mocks.
    assert score["summary"]["public_gates_status"] == "pass"
    assert score["summary"]["node_f1"] == 1.0
    assert manifest["evaluation"]["validation"]["overall_status"] == "pass"
    assert manifest["usage"]["llm_calls"] == 1
    # Prompt logs must not contain private vocabulary.
    prompt_text = (run_dir / "prompts" / "m3_ir.user.txt").read_text()
    assert "required_service_id" not in prompt_text
    assert "internal_spec" not in prompt_text


def test_m4_repair_loop_converges(workspace: Path, tmp_path: Path) -> None:
    broken = yaml.safe_load(_gold_serviceflow_yaml(workspace))
    for binding in broken["bindings"]:
        binding["service_id"] = "nonexistent_service_xyz"
    fixed_ir = _gold_serviceflow_yaml(workspace)
    script = {
        "m3_ir": yaml.safe_dump(broken, sort_keys=False),
        "m4_repair_1": fixed_ir,
    }
    manifest = run_one(
        "m4",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        repair_budget=3,
        client_factory=_stub_factory(script),
    )
    assert manifest["method_status"] == "completed"
    assert manifest["method_error"] is None
    assert manifest["usage"]["llm_calls"] == 2
    attempts = manifest["evaluation"]["repair_attempts"]
    assert attempts[0]["overall_status"] == "fail"
    assert attempts[0]["first_failing_gate"] == "G2"
    assert attempts[-1]["overall_status"] == "pass"
    assert len(attempts) == 2
    # The repair prompt must carry validator diagnostics.
    run_dir = tmp_path / "runs" / manifest["run_id"]
    repair_prompt = (run_dir / "prompts" / "m4_repair_1.user.txt").read_text()
    assert "G2_UNRESOLVED_SERVICE" in repair_prompt
    assert "nonexistent_service_xyz" in repair_prompt
    assert "required_service_id" not in repair_prompt  # no label leakage


def test_m4_repairs_initial_parse_error(workspace: Path, tmp_path: Path) -> None:
    fixed_ir = _gold_serviceflow_yaml(workspace)
    script = {
        "m3_ir": "this is not yaml at all: [unclosed",
        "m4_repair_parse": fixed_ir,
    }
    manifest = run_one(
        "m4",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        repair_budget=3,
        client_factory=_stub_factory(script),
    )
    assert manifest["method_status"] == "completed"
    attempts = manifest["evaluation"]["repair_attempts"]
    assert attempts[0]["synthetic"] is True
    assert attempts[0]["overall_status"] == "fail"
    assert attempts[-1]["overall_status"] == "pass"
    # The parse-seed repair prompt carries the broken output and diagnostic.
    run_dir = tmp_path / "runs" / manifest["run_id"]
    repair_prompt = (run_dir / "prompts" / "m4_repair_parse.user.txt").read_text()
    assert "G0_PARSE_ERROR" in repair_prompt
    assert "_unparseable_response.txt" in repair_prompt


def test_m4_parse_repairs_share_the_fixed_repair_budget(
    workspace: Path, tmp_path: Path
) -> None:
    script = {
        "m3_ir": "this is not yaml at all: [unclosed",
        "m4_repair_parse": "ir_version: [still unclosed",
        "m4_repair_parse_2": _gold_serviceflow_yaml(workspace),
    }
    manifest = run_one(
        "m4",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        repair_budget=2,
        client_factory=_stub_factory(script),
    )

    assert manifest["method_status"] == "completed"
    assert manifest["method_error"] is None
    assert manifest["usage"]["llm_calls"] == 3  # initial + exactly B repairs
    repair_stages = [
        stage["stage"]
        for stage in manifest["usage"]["per_stage"]
        if stage["stage"].startswith("m4_repair")
    ]
    assert repair_stages == ["m4_repair_parse", "m4_repair_parse_2"]
    # The repaired gold IR must pass every public gate. Private semantic
    # assertions are evaluated independently and may reject generic mocks.
    assert manifest["evaluation"]["score_summary"]["public_gates_status"] == "pass"


def test_m4_uses_remaining_budget_after_unparseable_repair(
    workspace: Path, tmp_path: Path
) -> None:
    broken = yaml.safe_load(_gold_serviceflow_yaml(workspace))
    for binding in broken["bindings"]:
        binding["service_id"] = "nonexistent_service_xyz"
    script = {
        "m3_ir": yaml.safe_dump(broken, sort_keys=False),
        "m4_repair_1": "ir_version: [unclosed",
        "m4_repair_2": _gold_serviceflow_yaml(workspace),
    }
    manifest = run_one(
        "m4",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        repair_budget=3,
        client_factory=_stub_factory(script),
    )

    assert manifest["method_status"] == "completed"
    assert manifest["usage"]["validator_calls"] == 2
    attempts = manifest["evaluation"]["repair_attempts"]
    assert attempts[0]["first_failing_gate"] == "G2"
    assert attempts[1]["synthetic"] is True
    assert attempts[1]["first_failing_gate"] == "G0"
    assert attempts[-1]["overall_status"] == "pass"
    run_dir = tmp_path / "runs" / manifest["run_id"]
    second_repair_prompt = (run_dir / "prompts" / "m4_repair_2.user.txt").read_text()
    assert "G0_PARSE_ERROR" in second_repair_prompt
    assert "_unparseable_response.txt" in second_repair_prompt


def test_m4_restores_best_candidate_after_later_regression(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def report(first_failure: str) -> dict:
        gates = []
        failed = False
        for gate_name in ("G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec"):
            if gate_name == first_failure:
                failed = True
                gates.append(
                    {
                        "gate": gate_name,
                        "status": "fail",
                        "description": gate_name,
                        "diagnostics": [
                            {"code": f"{gate_name}_TEST", "message": f"failure at {gate_name}"}
                        ],
                    }
                )
            else:
                gates.append(
                    {
                        "gate": gate_name,
                        "status": "pass" if not failed else "fail",
                        "description": gate_name,
                        "diagnostics": (
                            []
                            if not failed
                            else [
                                {
                                    "code": f"{gate_name}_DOWNSTREAM",
                                    "message": f"downstream failure at {gate_name}",
                                }
                            ]
                        ),
                    }
                )
        return {"overall_status": "fail", "first_failing_gate": first_failure, "gates": gates}

    reports = iter([report("G1"), report("G3"), report("G1")])
    monkeypatch.setattr(
        "prompt2serviceflow.experiments.methods.validate_submission",
        lambda *args, **kwargs: next(reports),
    )

    initial = yaml.safe_load(_gold_serviceflow_yaml(workspace))
    progressed = yaml.safe_load(_gold_serviceflow_yaml(workspace))
    regressed = yaml.safe_load(_gold_serviceflow_yaml(workspace))
    initial["service_intents"][0]["description"] = "initial candidate"
    progressed["service_intents"][0]["description"] = "best candidate"
    regressed["service_intents"][0]["description"] = "regressed candidate"
    ledger = UsageLedger()
    llm = StubLLMClient(
        MODEL,
        ledger,
        script={
            "m3_ir": yaml.safe_dump(initial, sort_keys=False),
            "m4_repair_1": yaml.safe_dump(progressed, sort_keys=False),
            "m4_repair_2": yaml.safe_dump(regressed, sort_keys=False),
        },
    )
    submission = tmp_path / "best-submission"
    result = run_m4(llm, workspace, submission, repair_budget=2)

    final_document = yaml.safe_load((submission / "serviceflow.yaml").read_text())
    assert final_document["service_intents"][0]["description"] == "best candidate"
    assert result.attempts[1]["selected_as_best"] is True
    assert result.attempts[2]["selected_as_best"] is False
    assert result.status == "completed"


def test_validator_budget_derivation() -> None:
    from prompt2serviceflow.experiments.methods import (
        DEFAULT_REPAIR_BUDGET,
        validator_budget_for,
    )

    assert DEFAULT_REPAIR_BUDGET == 3
    assert validator_budget_for(3) == 4
    assert validator_budget_for(0) == 1


def test_m4_budget_exhausted(workspace: Path, tmp_path: Path) -> None:
    broken = yaml.safe_load(_gold_serviceflow_yaml(workspace))
    for binding in broken["bindings"]:
        binding["service_id"] = "nonexistent_service_xyz"
    script = {
        "m3_ir": yaml.safe_dump(broken, sort_keys=False),
    }
    # Stub has no repair script: it re-returns the broken IR via default.
    manifest = run_one(
        "m4",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        repair_budget=1,
        client_factory=_stub_factory(script),
    )
    assert manifest["method_status"] == "parse_error" or (
        manifest["evaluation"]["repair_attempts"][-1]["overall_status"] == "fail"
    )


def test_run_manifest_contains_reproducibility_fields(workspace: Path, tmp_path: Path) -> None:
    manifest = run_one(
        "m0",
        workspace=workspace,
        instance_dir=INSTANCE,
        model=MODEL,
        runs_root=tmp_path / "runs",
        client_factory=_stub_factory({"m0_argo": "apiVersion: argoproj.io/v1alpha1\nkind: Workflow\nmetadata: {generateName: x-}\nspec: {}\n"}),
    )
    for key in (
        "run_id", "harness_version", "method", "prompt_version", "model",
        "instance", "catalog", "visible_input_policy", "environment",
        "started_at", "finished_at", "usage", "evaluation",
    ):
        assert key in manifest, key
    assert manifest["catalog"]["version"] == "0.1.0"
    usage = manifest["usage"]
    assert usage["total_tokens"] > 0
    assert "per_stage" in usage
