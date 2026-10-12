"""Tests for private gold-relative submission scoring.

Fixtures are built evaluation-side from gold artifacts (reference-quality
submissions) plus targeted corruptions. The scorer is private tooling; it
never ships in workspaces.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.experiments.scoring import _wiring_metrics, score_submission
from prompt2serviceflow.experiments.workspace import build_workspace


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmark"
AIRFLOW = BENCHMARK / "instances" / "main" / "airflow_db_cleanup"
FRAUD = BENCHMARK / "instances" / "main" / "fraud_detection_triage"


def _stage(instance_dir: Path, tmp_path: Path) -> tuple[Path, Path]:
    build_workspace(instance_dir, tmp_path, split="main", benchmark_root=BENCHMARK)
    workspace = tmp_path / "main" / instance_dir.name
    submission = workspace / "submission"
    submission.mkdir(exist_ok=True)
    serviceflow = yaml.safe_load((instance_dir / "gold" / "serviceflow.yaml").read_text())
    serviceflow["source"].pop("internal_spec_path", None)
    serviceflow["source"].pop("internal_spec_sha256", None)
    manifest = yaml.safe_load((workspace / "workspace.yaml").read_text())
    serviceflow["catalog_snapshot"] = {
        "catalog_id": "serviceflow_catalog",
        "version": manifest["catalog"]["version"],
        "sha256": manifest["catalog"]["sanitized_catalog_yaml_sha256"],
    }
    (submission / "serviceflow.yaml").write_text(
        yaml.safe_dump(serviceflow, sort_keys=False), encoding="utf-8"
    )
    shutil.copytree(instance_dir / "runtime", submission / "runtime")
    shutil.rmtree(submission / "runtime" / "scripts" / "__pycache__", ignore_errors=True)
    return workspace, submission


@pytest.fixture()
def airflow(tmp_path: Path) -> tuple[Path, Path]:
    return _stage(AIRFLOW, tmp_path)


def _rewrite_serviceflow(submission: Path, transform) -> None:
    path = submission / "serviceflow.yaml"
    document = yaml.safe_load(path.read_text())
    transform(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_reference_scores_perfect(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow
    report = score_submission(AIRFLOW, workspace, submission)
    summary = report["summary"]
    assert summary["full_pass_g0_g6"] is True
    assert summary["node_f1"] == 1.0
    assert summary["edge_f1"] == 1.0
    assert summary["binding_top1_accuracy"] == 1.0
    assert summary["wiring_f1"] == 1.0
    assert summary["g6_assert_pass_rate"] == 1.0
    binding = report["binding"]
    assert binding["confusion_by_label"] == {}
    assert binding["version_accuracy_given_correct_service"] == 1.0
    graph = report["graph"]
    assert graph["alignment"]["matched"] == graph["alignment"]["gold_intents"]
    assert graph["over_decomposition_rate"] == 0.0
    assert graph["under_decomposition_rate"] == 0.0
    assert graph["source_step_coverage"]["rate"] == 1.0
    assert report["g6_assert"]["overall_status"] == "pass"


def test_empty_submission_is_unscored(airflow: tuple[Path, Path]) -> None:
    workspace, _ = airflow
    empty = workspace / "submission"
    for child in empty.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    report = score_submission(AIRFLOW, workspace, empty)
    assert report["summary"]["full_pass_g0_g6"] is False
    assert report["graph"]["status"] == "unscored"
    assert report["binding"]["status"] == "unscored"
    assert report["summary"]["node_f1"] is None


def test_empty_gold_and_submission_wiring_is_not_applicable() -> None:
    empty = {"service_intents": [], "artifacts": []}
    metrics = _wiring_metrics(empty, empty, {})
    assert metrics["status"] == "not_applicable"
    assert metrics["applicable"] is False
    assert metrics["f1"] is None


def test_schema_invalid_artifact_is_recorded_not_fatal(
    airflow: tuple[Path, Path],
) -> None:
    workspace, submission = airflow

    def transform(document: dict) -> None:
        document["artifacts"][0].pop("producer")

    _rewrite_serviceflow(submission, transform)
    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    assert report["public_gates"]["overall_status"] == "fail"
    assert report["graph"]["status"] == "unscored"
    assert "malformed submission structure" in report["graph"]["reason"]


def test_distractor_confusion_is_classified(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow

    def transform(document: dict) -> None:
        for binding in document["bindings"]:
            if binding["intent_id"] == "cleanup_dag_run":
                # contract-mismatch distractor in this intent's candidate set.
                binding["service_id"] = "postgres_parameterized_sql_executor"

    _rewrite_serviceflow(submission, transform)
    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    binding = report["binding"]
    assert binding["confusion_by_label"].get("contract_mismatch") == 1
    assert binding["top1_accuracy"] < 1.0
    outcomes = {item["gold_intent"]: item["outcome"] for item in binding["per_intent"]}
    assert outcomes["cleanup_dag_run"] == "contract_mismatch"


def test_invented_service_is_counted(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow

    def transform(document: dict) -> None:
        document["bindings"][0]["service_id"] = "nonexistent_service_xyz"

    _rewrite_serviceflow(submission, transform)
    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    binding = report["binding"]
    assert binding["confusion_by_label"].get("invented_service") == 1
    assert binding["rates"]["invented_service"] > 0.0


def test_version_error_tracked_separately(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow

    def transform(document: dict) -> None:
        document["bindings"][0]["service_version"] = "9.9.9"

    _rewrite_serviceflow(submission, transform)
    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    binding = report["binding"]
    assert binding["version_accuracy_given_correct_service"] is not None
    assert binding["version_accuracy_given_correct_service"] < 1.0


def test_alignment_is_robust_to_renamed_intents(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow

    def transform(document: dict) -> None:
        # Rename one intent everywhere; alignment via source-step refs and I/O
        # signatures should still recover it.
        old = "cleanup_dag_run"
        new = "purge_old_dag_runs"
        for intent in document["service_intents"]:
            if intent["intent_id"] == old:
                intent["intent_id"] = new
        for binding in document["bindings"]:
            if binding["intent_id"] == old:
                binding["intent_id"] = new
        for edge in document["control_flow"]["edges"]:
            if edge["from"] == old:
                edge["from"] = new
            if edge["to"] == old:
                edge["to"] = new
        for item in document.get("source_step_accounting", []):
            item["intent_ids"] = [
                new if item_id == old else item_id for item_id in item["intent_ids"]
            ]

    _rewrite_serviceflow(submission, transform)
    manifest_path = submission / "runtime" / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    for task in manifest["tasks"]:
        if task["intent_id"] == "cleanup_dag_run":
            task["intent_id"] = "purge_old_dag_runs"
        task["dependencies"] = [
            "purge_old_dag_runs" if dep == "cleanup_dag_run" else dep
            for dep in task.get("dependencies", [])
        ]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    graph = report["graph"]
    assert graph["alignment"]["mapping"].get("purge_old_dag_runs") == "cleanup_dag_run"
    assert graph["node"]["f1"] == 1.0


def test_g6_assert_catches_semantic_failure(tmp_path: Path) -> None:
    workspace, submission = _stage(FRAUD, tmp_path)
    # Force a low risk score: execution still succeeds (auto-approve branch),
    # but the high-risk scenario's assertions must fail.
    script = submission / "runtime" / "scripts" / "01_analyze_transactions.py"
    with script.open("a", encoding="utf-8") as handle:
        handle.write(
            "\nimport json as _json, sys as _sys\n"
            "from pathlib import Path as _Path\n"
            "_ws = _Path(_sys.argv[_sys.argv.index('--workspace') + 1])\n"
            "_p = _ws / 'artifacts' / 'risk_score.json'\n"
            "_d = _json.loads(_p.read_text())\n"
            "_d['score'] = 0.1\n"
            "_p.write_text(_json.dumps(_d))\n"
        )
    report = score_submission(FRAUD, workspace, submission)
    assert report["summary"]["full_pass_g0_g6"] is False
    # The split in action: execution and contract conformance still pass
    # publicly; only the private assertion evaluation fails.
    public_g6 = next(gate for gate in report["public_gates"]["gates"] if gate["gate"] == "G6-Exec")
    assert public_g6["status"] == "pass"
    assert report["g6_assert"]["overall_status"] == "fail"
    assert report["g6_assert"]["pass_rate"] < 1.0
    high_risk = next(
        item
        for item in report["g6_assert"]["scenarios"]
        if item["scenario"] == "high_risk_manual_review"
    )
    failed = {item["assertion_id"] for item in high_risk["assertions"] if item["status"] != "pass"}
    assert "high_risk_score" in failed


def test_malformed_manifest_is_recorded_not_fatal(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow
    # A model emitting unquoted {fixtures}/... tokens produces invalid YAML;
    # the scorer must record it as an unscored method failure, not crash.
    manifest_path = submission / "runtime" / "manifest.yaml"
    manifest_path.write_text(
        "tasks:\n  - intent_id: x\n    arguments:\n      - {fixtures}/data.csv\n",
        encoding="utf-8",
    )
    report = score_submission(AIRFLOW, workspace, submission)
    assert report["g6_assert"]["status"] == "unscored"
    assert "does not parse" in report["g6_assert"]["reason"]
    assert report["summary"]["full_pass_g0_g6"] is False


def test_null_collections_in_ir_are_tolerated(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow

    def transform(document: dict) -> None:
        document["control_flow"]["edges"] = None
        document["artifacts"] = None

    _rewrite_serviceflow(submission, transform)
    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    # Scored (not crashed), with degraded metrics reflecting the nulls.
    assert report["graph"]["edge"]["f1"] == 0.0
    assert report["summary"]["public_gates_status"] == "fail"


def test_mrr_is_null_with_note(airflow: tuple[Path, Path]) -> None:
    workspace, submission = airflow
    report = score_submission(AIRFLOW, workspace, submission, run_execution=False)
    assert report["binding"]["mean_reciprocal_rank"] is None
    assert "mrr_note" in report["binding"]
