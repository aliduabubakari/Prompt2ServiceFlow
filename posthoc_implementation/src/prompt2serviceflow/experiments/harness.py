"""Run harness: orchestration, manifests, logging, and batch summaries.

Implements the reproducibility contract of plan Section 14: every run
produces a manifest with system ID, prompt version, model version, decoding
settings, catalog snapshot, visible-input policy, raw responses, parsed
artifacts, validator reports, scoring outputs, token/latency/cost, and
environment metadata.

Run directory layout::

    experiments/runs/<run_id>/
      manifest.json
      prompts/<stage>.system.txt, prompts/<stage>.user.txt
      responses/<stage>.txt
      submission/...            # M3/M4 submission package
      argo_generated/...        # M0-M2 raw Argo (+ dag.json for M1)
      validation.json           # public gates (M3/M4)
      score.json                # private gold-relative scoring (M3/M4)
      argo_assessment.json      # structural assessment (M0-M2)
      direct_score.json         # extraction-based scoring (M0-M2)
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from prompt2serviceflow.experiments import prompts
from prompt2serviceflow.experiments.direct_argo import assess_direct_argo, score_direct_argo
from prompt2serviceflow.experiments.llm import (
    LLMClient,
    ModelConfig,
    OpenAICompatibleClient,
    UsageLedger,
)
from prompt2serviceflow.experiments.methods import (
    METHOD_IDS,
    METHOD_NAMES,
    MethodResult,
    run_m0,
    run_m1,
    run_m2,
    run_m3,
    run_m4,
)
from prompt2serviceflow.experiments.scoring import score_submission
from prompt2serviceflow.experiments.runtime_compiler import RUNTIME_COMPILER_VERSION
from prompt2serviceflow.experiments.submission import validate_submission

HARNESS_VERSION = "2.2.2"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS_ROOT = REPO_ROOT / "experiments" / "runs"

ClientFactory = Callable[[ModelConfig, UsageLedger], LLMClient]


def _default_client_factory(config: ModelConfig, ledger: UsageLedger) -> LLMClient:
    return OpenAICompatibleClient(config, ledger)


def _file_sha256(path: Path) -> str | None:
    import hashlib

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )
    except OSError:
        return None
    return completed.stdout.strip() or None


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _persist_stages(run_dir: Path, result: MethodResult) -> None:
    for stage in result.stages:
        (run_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "responses").mkdir(parents=True, exist_ok=True)
        (run_dir / "prompts" / f"{stage.stage}.system.txt").write_text(
            stage.system, encoding="utf-8"
        )
        (run_dir / "prompts" / f"{stage.stage}.user.txt").write_text(stage.user, encoding="utf-8")
        (run_dir / "responses" / f"{stage.stage}.txt").write_text(
            stage.raw_response, encoding="utf-8"
        )


def run_one(
    method_id: str,
    *,
    workspace: Path,
    instance_dir: Path,
    model: ModelConfig,
    runs_root: Path = DEFAULT_RUNS_ROOT,
    repair_budget: int = 3,
    run_execution: bool = True,
    repair_with_execution: bool | None = None,
    client_factory: ClientFactory | None = None,
    batch_id: str | None = None,
    sample_index: int = 0,
    freeze_document: dict[str, Any] | None = None,
    roster_path: Path | None = None,
    freeze_path: Path | None = None,
    ablation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one method on one instance and write the full run record."""
    if method_id not in METHOD_IDS:
        raise ValueError(f"unknown method id: {method_id!r}")
    workspace = workspace.resolve()
    instance_dir = instance_dir.resolve()
    workspace_manifest = prompts.load_workspace_manifest(workspace)
    split = workspace_manifest["instance"]["split"]
    instance_id = workspace_manifest["instance"]["id"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    nonce = uuid.uuid4().hex[:8]
    run_id = (
        f"{method_id}__{split}__{instance_id}__{model.model_id}__"
        f"s{sample_index}__{timestamp}__{nonce}"
    )
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ledger = UsageLedger()
    factory = client_factory or _default_client_factory
    started = datetime.now(timezone.utc)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "batch_id": batch_id,
        "sample_index": sample_index,
        "ablation": ablation,
        "harness_version": HARNESS_VERSION,
        "method": {"id": method_id, "name": METHOD_NAMES[method_id]},
        "prompt_version": prompts.PROMPT_VERSION,
        "runtime_compiler_version": RUNTIME_COMPILER_VERSION,
        "model": {
            "model_id": model.model_id,
            "model_name": model.model_name,
            "base_url": model.base_url,
            "temperature": model.temperature,
            "top_p": model.top_p,
            "seed": model.seed,
            "max_tokens": model.max_tokens,
            "context_window": model.context_window,
        },
        "instance": {
            "id": instance_id,
            "split": split,
            "benchmark_id": workspace_manifest["instance"]["benchmark_id"],
        },
        "catalog": workspace_manifest["catalog"],
        "roster_sha256": _file_sha256(
            (roster_path or REPO_ROOT / "experiments" / "config" / "models.json").resolve()
        ),
        "workspace_manifest_sha256": _file_sha256(workspace / "workspace.yaml"),
        "freeze": (
            {
                "freeze_id": freeze_document.get("freeze_id"),
                "status": freeze_document.get("status"),
                "sha256": _file_sha256(
                    (freeze_path or REPO_ROOT / "experiments" / "config" / "freeze.json").resolve()
                ),
            }
            if freeze_document
            else None
        ),
        "visible_input_policy": {
            "method_view": prompts.VISIBLE_VIEWS[method_id],
            "workspace_manifest": str(workspace / "workspace.yaml"),
        },
        "repair": (
            {
                "budget": repair_budget,
                "execution_feedback": (
                    run_execution if repair_with_execution is None else repair_with_execution
                ),
            }
            if method_id == "m4"
            else None
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "git_revision": _git_revision(),
        },
        "started_at": started.isoformat(),
    }

    result = MethodResult(method_id=method_id, status="init")
    try:
        client = factory(model, ledger)
        if method_id == "m0":
            result = run_m0(client, workspace, ablation=ablation)
        elif method_id == "m1":
            result = run_m1(client, workspace, ablation=ablation)
        elif method_id == "m2":
            result = run_m2(client, workspace, ablation=ablation)
        elif method_id == "m3":
            result = run_m3(client, workspace, run_dir / "submission", ablation=ablation)
        else:
            result = run_m4(
                client,
                workspace,
                run_dir / "submission",
                repair_budget=repair_budget,
                repair_with_execution=(
                    run_execution if repair_with_execution is None else repair_with_execution
                ),
                ablation=ablation,
            )
    except Exception as exc:
        result.status = "llm_error"
        result.error = str(exc)

    _persist_stages(run_dir, result)
    manifest["method_status"] = result.status
    manifest["method_error"] = result.error
    ledger.validator_calls = result.validator_calls

    # Evaluation phase (evaluation-side: validation + private scoring).
    # Guarded: a malformed method output must be recorded as that method's
    # failure, never crash the harness mid-batch (plan Section 11: parser/
    # format violations are a reported metric, not a harness error).
    evaluation: dict[str, Any] = {}
    if result.status == "completed":
        try:
            evaluation = _evaluate_run(
                method_id, result, workspace, instance_dir, run_dir, ledger, run_execution
            )
        except Exception as exc:
            evaluation = {"error": f"evaluation failed: {exc}"}
    if result.attempts:
        evaluation["repair_attempts"] = [
            {key: value for key, value in attempt.items() if key != "report"}
            for attempt in result.attempts
        ]
    manifest["evaluation"] = evaluation
    manifest["usage"] = ledger.summary(model)
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(run_dir / "manifest.json", manifest)
    return manifest


def _evaluate_run(
    method_id: str,
    result: MethodResult,
    workspace: Path,
    instance_dir: Path,
    run_dir: Path,
    ledger: UsageLedger,
    run_execution: bool,
) -> dict[str, Any]:
    evaluation: dict[str, Any] = {}
    if method_id in ("m0", "m1", "m2"):
        argo_text = result.outputs.get("argo_yaml", "")
        (run_dir / "argo_generated").mkdir(exist_ok=True)
        (run_dir / "argo_generated" / "workflow.yaml").write_text(argo_text, encoding="utf-8")
        if "dag_json" in result.outputs:
            (run_dir / "argo_generated" / "dag.json").write_text(
                result.outputs["dag_json"], encoding="utf-8"
            )
        assessment = assess_direct_argo(argo_text, workspace)
        _write_json(run_dir / "argo_assessment.json", assessment)
        direct_score = score_direct_argo(assessment, instance_dir, workspace)
        _write_json(run_dir / "direct_score.json", direct_score)
        evaluation["argo_assessment"] = {
            "yaml_parse": assessment.get("yaml_parse"),
            "documents": assessment.get("documents"),
            "referenced_service_count": (
                assessment.get("service_extraction", {}).get("reference_count")
            ),
        }
        evaluation["direct_score"] = {
            key: direct_score[key]
            for key in (
                "service_grounded",
                "service_precision",
                "service_recall",
                "distractor_confusion",
                "out_of_catalog_references",
                "node_f1",
                "edge_f1",
                "gate_statuses",
                "full_pass_g0_g6",
            )
        }
    else:
        validation = validate_submission(
            workspace, run_dir / "submission", run_execution=run_execution
        )
        ledger.evaluation_validator_calls += 2  # explicit validation + scorer drift re-run
        _write_json(run_dir / "validation.json", validation)
        score = score_submission(
            instance_dir, workspace, run_dir / "submission", run_execution=run_execution
        )
        _write_json(run_dir / "score.json", score)
        evaluation["validation"] = {
            "overall_status": validation["overall_status"],
            "first_failing_gate": validation["first_failing_gate"],
            "gate_statuses": {gate["gate"]: gate["status"] for gate in validation["gates"]},
        }
        evaluation["score_summary"] = score["summary"]
    return evaluation


def run_batch(
    method_ids: list[str],
    *,
    workspaces_root: Path,
    benchmark_root: Path,
    model: ModelConfig,
    splits: tuple[str, ...] = ("main", "validation"),
    instance_ids: list[str] | None = None,
    limit: int | None = None,
    runs_root: Path = DEFAULT_RUNS_ROOT,
    repair_budget: int = 3,
    run_execution: bool = True,
    repair_with_execution: bool | None = None,
    client_factory: ClientFactory | None = None,
    samples_per_instance: int = 1,
    allow_unfrozen: bool = False,
    allow_validation_rerun: bool = False,
    freeze_path: Path | None = None,
    roster_path: Path | None = None,
    ablation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run methods over instances and write a batch summary."""
    from prompt2serviceflow.experiments.freeze import (
        DEFAULT_FREEZE_PATH,
        DEFAULT_ROSTER_PATH,
        FreezeError,
        check_freeze,
    )
    from prompt2serviceflow.experiments.leakage import scan_workspace_root

    if samples_per_instance < 1:
        raise ValueError("samples_per_instance must be at least 1")
    freeze, freeze_errors = check_freeze(
        freeze_path=freeze_path or DEFAULT_FREEZE_PATH,
        roster_path=roster_path or DEFAULT_ROSTER_PATH,
        repair_budget=repair_budget,
        model_id=model.model_id,
        require_frozen=not allow_unfrozen,
    )
    if freeze_errors and not allow_unfrozen:
        raise FreezeError("; ".join(freeze_errors))
    leakage = scan_workspace_root(workspaces_root)
    if leakage["status"] != "pass":
        raise RuntimeError(
            f"workspace leakage gate failed with {leakage['finding_count']} findings"
        )
    validation_lock = runs_root / "validation_lock.json"
    if "validation" in splits and validation_lock.exists() and not allow_validation_rerun:
        raise RuntimeError(
            f"Validation-20 is locked by {validation_lock}; pass allow_validation_rerun only "
            "for an explicitly documented invalidation/recovery run"
        )
    batch_id = (
        f"batch__{model.model_id}__"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__{uuid.uuid4().hex[:8]}"
    )
    manifests: list[dict[str, Any]] = []
    selected: list[tuple[str, Path, Path]] = []
    for split in splits:
        split_dir = workspaces_root / split
        if not split_dir.is_dir():
            continue
        for workspace in sorted(split_dir.iterdir()):
            if not (workspace / "workspace.yaml").is_file():
                continue
            if instance_ids and workspace.name not in instance_ids:
                continue
            instance_dir = benchmark_root / "instances" / split / workspace.name
            if not instance_dir.is_dir():
                continue
            selected.append((split, workspace, instance_dir))
    if limit is not None:
        selected = selected[:limit]
    if instance_ids:
        found = {workspace.name for _, workspace, _ in selected}
        missing = sorted(set(instance_ids) - found)
        if missing:
            raise ValueError(f"requested instances not found: {missing}")
    if not selected:
        raise ValueError("no experiment instances selected")
    for _, workspace, instance_dir in selected:
        for method_id in method_ids:
            for sample_index in range(samples_per_instance):
                manifests.append(
                    run_one(
                        method_id,
                        workspace=workspace,
                        instance_dir=instance_dir,
                        model=model,
                        runs_root=runs_root,
                        repair_budget=repair_budget,
                        run_execution=run_execution,
                        repair_with_execution=repair_with_execution,
                        client_factory=client_factory,
                        batch_id=batch_id,
                        sample_index=sample_index,
                        freeze_document=freeze,
                        roster_path=roster_path or DEFAULT_ROSTER_PATH,
                        freeze_path=freeze_path or DEFAULT_FREEZE_PATH,
                        ablation=ablation,
                    )
                )
    summary = {
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_id": batch_id,
        "freeze_id": freeze.get("freeze_id"),
        "freeze_errors_ignored": freeze_errors if allow_unfrozen else [],
        "samples_per_instance": samples_per_instance,
        "ablation": ablation,
        "harness_version": HARNESS_VERSION,
        "runtime_compiler_version": RUNTIME_COMPILER_VERSION,
        "model": {"model_id": model.model_id, "model_name": model.model_name},
        "run_count": len(manifests),
        "expected_cell_count": len(manifests),
        "recorded_cell_count": len(manifests),
        "runs": [
            {
                "run_id": manifest["run_id"],
                "manifest_path": str((runs_root / manifest["run_id"] / "manifest.json").resolve()),
                "sample_index": manifest["sample_index"],
                "method": manifest["method"]["id"],
                "instance": manifest["instance"]["id"],
                "split": manifest["instance"]["split"],
                "method_status": manifest["method_status"],
                "evaluation": manifest["evaluation"],
                "usage": {
                    key: manifest["usage"][key]
                    for key in (
                        "llm_calls",
                        "total_tokens",
                        "latency_s",
                        "cost_usd",
                        "validator_calls",
                        "evaluation_validator_calls",
                    )
                },
            }
            for manifest in manifests
        ],
    }
    summary_path = runs_root / f"{batch_id}.json"
    _write_json(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    if "validation" in splits and not allow_unfrozen:
        _write_json(
            validation_lock,
            {
                "freeze_id": freeze.get("freeze_id"),
                "batch_id": batch_id,
                "batch_summary": str(summary_path),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    return summary


if __name__ == "__main__":
    sys.exit("use scripts/run_experiment.py")
