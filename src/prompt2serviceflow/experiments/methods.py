"""Method runners M0-M4 (the LLM lives only here, inside the method boundary).

Each runner consumes a visible view of the workspace (built by
``prompts.py``), calls the LLM, parses outputs deterministically, and writes
the submission package. Repair-enabled M4 additionally calls the public
validator and feeds structured diagnostics back to the model under a fixed
budget (plan Sections 2 and 11).

Runners write submissions to ``submission_dir`` (a run-local directory managed
by the harness); the workspace itself is treated as read-only input.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from prompt2serviceflow.experiments import prompts
from prompt2serviceflow.experiments.extractors import (
    extract_fenced_or_raw,
    extract_yaml_document,
)
from prompt2serviceflow.experiments.llm import LLMClient
from prompt2serviceflow.experiments.runtime_compiler import materialize_runtime
from prompt2serviceflow.experiments.submission import validate_submission

# Locked repair budget (plan Section 17, D4): M4 performs an initial
# validation plus up to B repairs; the M5 validator-call budget is derived
# as B + 1 so the two controllers are compared at matched feedback.
DEFAULT_REPAIR_BUDGET = 3
GATE_ORDER = ("G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec")


def validator_budget_for(repair_budget: int) -> int:
    """M5 validator-call budget matched to an M4 budget (initial + B)."""
    return repair_budget + 1


METHOD_IDS = ("m0", "m1", "m2", "m3", "m4")
METHOD_NAMES = {
    "m0": "Direct2Argo",
    "m1": "Prompt2DAG-Argo",
    "m2": "Catalogue-Grounded Argo",
    "m3": "Contract-first ServiceFlowIR",
    "m4": "Contract-first ServiceFlowIR + repair",
}


@dataclass
class StageLog:
    stage: str
    system: str
    user: str
    raw_response: str


@dataclass
class MethodResult:
    method_id: str
    status: str  # "completed" | "parse_error" | "llm_error"
    error: str | None = None
    stages: list[StageLog] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)  # M0-M2 raw artifacts
    attempts: list[dict[str, Any]] = field(default_factory=list)  # M4 repair log
    validator_calls: int = 0


def _read_submission_files(submission_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in [submission_dir / "serviceflow.yaml"]:
        if path.is_file() and "__pycache__" not in path.parts:
            files[path.relative_to(submission_dir).as_posix()] = path.read_text(encoding="utf-8")
    return files


def _write_ir_and_compile(workspace: Path, submission_dir: Path, document: dict[str, Any]) -> str | None:
    """Write model-authored IR and refresh all deterministic derived files."""

    submission_dir.mkdir(parents=True, exist_ok=True)
    (submission_dir / "serviceflow.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    try:
        materialize_runtime(workspace, submission_dir)
    except Exception as exc:
        # Invalid IR is deliberately left in place so G0 can return structured
        # diagnostics to M4. A stale runtime must never survive a failed build.
        runtime = submission_dir / "runtime"
        if runtime.exists():
            import shutil

            shutil.rmtree(runtime)
        return str(exc)
    return None


def _call(llm: LLMClient, result: MethodResult, stage: str, system: str, user: str) -> str:
    response = llm.complete(stage=stage, system=system, user=user)
    result.stages.append(
        StageLog(stage=stage, system=system, user=user, raw_response=response.text)
    )
    return response.text


def _report_fingerprint(report: dict[str, Any]) -> tuple[Any, ...]:
    """Return a stable fingerprint for detecting repeated validator states."""

    failures: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for gate in report.get("gates", []):
        if gate.get("status") != "fail":
            continue
        diagnostics = tuple(
            sorted(
                (str(item.get("code", "")), str(item.get("message", "")))
                for item in gate.get("diagnostics", [])
            )
        )
        failures.append((str(gate.get("gate", "")), diagnostics))
    return tuple(failures)


def _report_rank(report: dict[str, Any]) -> tuple[int, int, int, int]:
    """Rank candidates by gate progress, then breadth and diagnostic count.

    The prefix term makes a candidate that reaches G3 preferable to one that
    regresses to G1, even if the latter happens to pass more later gates. This
    fixed ordering uses only public validator outputs.
    """

    statuses = {str(gate.get("gate")): gate.get("status") for gate in report.get("gates", [])}
    prefix = 0
    for gate in GATE_ORDER:
        if statuses.get(gate) != "pass":
            break
        prefix += 1
    passed = sum(status == "pass" for status in statuses.values())
    diagnostic_count = sum(
        len(gate.get("diagnostics", []))
        for gate in report.get("gates", [])
        if gate.get("status") == "fail"
    )
    return (int(report.get("overall_status") == "pass"), prefix, passed, -diagnostic_count)


def _attempt_record(
    report: dict[str, Any],
    *,
    attempt: int,
    selected_as_best: bool,
    repeated_state: bool,
    synthetic: bool = False,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "overall_status": report.get("overall_status", "fail"),
        "first_failing_gate": report.get("first_failing_gate"),
        "gate_statuses": {
            gate["gate"]: gate["status"] for gate in report.get("gates", [])
        },
        "selected_as_best": selected_as_best,
        "repeated_state": repeated_state,
        "synthetic": synthetic,
        "report": None,
    }


def _parse_failure_report(message: str) -> dict[str, Any]:
    return {
        "overall_status": "fail",
        "gates": [
            {
                "gate": "G0",
                "status": "fail",
                "description": "Parse/schema validity of the submission package",
                "diagnostics": [{"code": "G0_PARSE_ERROR", "message": message}],
            }
        ],
        "first_failing_gate": "G0",
    }


# ---------------------------------------------------------------------------
# M0: Direct2Argo
# ---------------------------------------------------------------------------


def run_m0(
    llm: LLMClient, workspace: Path, *, ablation: dict[str, Any] | None = None
) -> MethodResult:
    result = MethodResult(method_id="m0", status="completed")
    view = prompts.build_visible_view(workspace, "m0", ablation=ablation)
    system, user = prompts.m0_prompts(view)
    text = _call(llm, result, "m0_argo", system, user)
    result.outputs["argo_yaml"] = extract_fenced_or_raw(text)
    return result


# ---------------------------------------------------------------------------
# M1: Prompt2DAG-Argo
# ---------------------------------------------------------------------------


def run_m1(
    llm: LLMClient, workspace: Path, *, ablation: dict[str, Any] | None = None
) -> MethodResult:
    result = MethodResult(method_id="m1", status="completed")
    view = prompts.build_visible_view(workspace, "m1", ablation=ablation)
    system, user = prompts.m1_stage1_prompts(view)
    dag_text = _call(llm, result, "m1_dag", system, user)
    result.outputs["dag_json"] = dag_text
    try:
        json.loads(dag_text.strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError as exc:
        result.status = "parse_error"
        result.error = f"stage 1 DAG is not valid JSON: {exc}"
        return result
    system, user = prompts.m1_stage2_prompts(view, dag_text)
    argo_text = _call(llm, result, "m1_argo", system, user)
    result.outputs["argo_yaml"] = extract_fenced_or_raw(argo_text)
    return result


# ---------------------------------------------------------------------------
# M2: Catalogue-Grounded Argo
# ---------------------------------------------------------------------------


def run_m2(
    llm: LLMClient, workspace: Path, *, ablation: dict[str, Any] | None = None
) -> MethodResult:
    result = MethodResult(method_id="m2", status="completed")
    view = prompts.build_visible_view(workspace, "m2", ablation=ablation)
    system, user = prompts.m2_prompts(view)
    text = _call(llm, result, "m2_argo", system, user)
    result.outputs["argo_yaml"] = extract_fenced_or_raw(text)
    return result


# ---------------------------------------------------------------------------
# M3: Contract-first ServiceFlowIR
# ---------------------------------------------------------------------------


def _run_m3_stages(
    llm: LLMClient,
    workspace: Path,
    submission_dir: Path,
    result: MethodResult,
    *,
    ablation: dict[str, Any] | None = None,
) -> MethodResult:
    submission_dir.mkdir(parents=True, exist_ok=True)
    view = prompts.build_visible_view(workspace, result.method_id, ablation=ablation)
    workspace_manifest = prompts.load_workspace_manifest(workspace)

    system, user = prompts.m3_ir_prompts(view, workspace_manifest)
    ir_text = _call(llm, result, "m3_ir", system, user)
    document, error = extract_yaml_document(ir_text)
    if error or not isinstance(document, dict):
        result.status = "parse_error"
        result.error = f"ServiceFlowIR output is not a parseable YAML document: {error}"
        return result
    compile_error = _write_ir_and_compile(workspace, submission_dir, document)
    if compile_error:
        result.error = f"deterministic runtime compilation failed: {compile_error}"
    return result


def run_m3(
    llm: LLMClient,
    workspace: Path,
    submission_dir: Path,
    *,
    ablation: dict[str, Any] | None = None,
) -> MethodResult:
    result = MethodResult(method_id="m3", status="completed")
    return _run_m3_stages(llm, workspace, submission_dir, result, ablation=ablation)


# ---------------------------------------------------------------------------
# M4: Contract-first ServiceFlowIR + bounded diagnostic repair
# ---------------------------------------------------------------------------


def run_m4(
    llm: LLMClient,
    workspace: Path,
    submission_dir: Path,
    *,
    repair_budget: int = DEFAULT_REPAIR_BUDGET,
    repair_with_execution: bool = True,
    ablation: dict[str, Any] | None = None,
) -> MethodResult:
    result = MethodResult(method_id="m4", status="completed")
    _run_m3_stages(llm, workspace, submission_dir, result, ablation=ablation)
    view = prompts.build_visible_view(workspace, "m4", ablation=ablation)
    diagnostic_history: list[dict[str, Any]] = []
    seen_states: set[tuple[Any, ...]] = set()
    best_document: dict[str, Any] | None = None
    best_report: dict[str, Any] | None = None
    best_rank: tuple[int, int, int, int] | None = None
    repairs_used = 0

    # A format failure in the generation stages is a repairable G0-level
    # failure, not a dead end: seed the loop with a synthetic parse
    # diagnostic (no validator call is consumed for it).
    parse_seed = result.status == "parse_error"
    if parse_seed:
        broken = _parse_failure_report(result.error or "output not parseable")
        diagnostic_history.append(broken)
        seen_states.add(_report_fingerprint(broken))
        result.attempts.append(
            _attempt_record(
                broken,
                attempt=0,
                selected_as_best=False,
                repeated_state=False,
                synthetic=True,
            )
        )
        unparseable_response = result.stages[-1].raw_response if result.stages else ""
        current_parse_report = broken
        while repairs_used < repair_budget:
            submission_files = _read_submission_files(submission_dir)
            submission_files["_unparseable_response.txt"] = unparseable_response
            system, user = prompts.m4_repair_prompts(
                view,
                submission_files,
                current_parse_report,
                diagnostic_history=diagnostic_history,
            )
            stage = (
                "m4_repair_parse"
                if repairs_used == 0
                else f"m4_repair_parse_{repairs_used + 1}"
            )
            repair_text = _call(llm, result, stage, system, user)
            repairs_used += 1
            document, error = extract_yaml_document(repair_text)
            if not error and isinstance(document, dict):
                _write_ir_and_compile(workspace, submission_dir, document)
                result.status = "completed"
                result.error = None
                break

            result.status = "parse_error"
            result.error = (
                f"parse-seed repair {repairs_used} is not a ServiceFlowIR YAML document: {error}"
            )
            current_parse_report = _parse_failure_report(result.error)
            diagnostic_history.append(current_parse_report)
            fingerprint = _report_fingerprint(current_parse_report)
            repeated_state = fingerprint in seen_states
            seen_states.add(fingerprint)
            result.attempts.append(
                _attempt_record(
                    current_parse_report,
                    attempt=len(result.attempts),
                    selected_as_best=False,
                    repeated_state=repeated_state,
                    synthetic=True,
                )
            )
            unparseable_response = repair_text
        else:
            return result

    # A repair call consumes one unit of B even when its response is not
    # parseable. Such a response is itself a G0 failure: feed the raw response
    # and parse diagnostic into the next remaining repair call instead of
    # terminating the controller prematurely. Validator calls remain bounded
    # by the initial call plus one call for each parseable repair (<= B + 1).
    report = validate_submission(workspace, submission_dir, run_execution=repair_with_execution)
    result.validator_calls += 1
    diagnostic_history.append(report)
    fingerprint = _report_fingerprint(report)
    repeated_state = fingerprint in seen_states
    seen_states.add(fingerprint)
    serviceflow_path = submission_dir / "serviceflow.yaml"
    best_document = yaml.safe_load(serviceflow_path.read_text(encoding="utf-8"))
    best_report = report
    best_rank = _report_rank(report)
    result.attempts.append(
        _attempt_record(
            report,
            attempt=len(result.attempts),
            selected_as_best=True,
            repeated_state=repeated_state,
        )
    )
    if report["overall_status"] == "pass":
        return result

    unparseable_response: str | None = None
    while repairs_used < repair_budget:
        repair_number = repairs_used + 1
        submission_files = _read_submission_files(submission_dir)
        if unparseable_response is not None:
            submission_files["_unparseable_response.txt"] = unparseable_response
        system, user = prompts.m4_repair_prompts(
            view,
            submission_files,
            best_report,
            diagnostic_history=diagnostic_history,
        )
        repair_text = _call(llm, result, f"m4_repair_{len(result.attempts)}", system, user)
        repairs_used += 1
        document, error = extract_yaml_document(repair_text)
        if error or not isinstance(document, dict):
            result.status = "parse_error"
            result.error = (
                f"repair attempt {repair_number} is not a ServiceFlowIR YAML document: {error}"
            )
            parse_report = _parse_failure_report(result.error)
            diagnostic_history.append(parse_report)
            fingerprint = _report_fingerprint(parse_report)
            repeated_state = fingerprint in seen_states
            seen_states.add(fingerprint)
            result.attempts.append(
                _attempt_record(
                    parse_report,
                    attempt=len(result.attempts),
                    selected_as_best=False,
                    repeated_state=repeated_state,
                    synthetic=True,
                )
            )
            unparseable_response = repair_text
            continue

        result.status = "completed"
        result.error = None
        unparseable_response = None
        _write_ir_and_compile(workspace, submission_dir, document)
        candidate_report = validate_submission(
            workspace,
            submission_dir,
            run_execution=repair_with_execution,
        )
        result.validator_calls += 1
        diagnostic_history.append(candidate_report)
        fingerprint = _report_fingerprint(candidate_report)
        repeated_state = fingerprint in seen_states
        seen_states.add(fingerprint)
        candidate_rank = _report_rank(candidate_report)
        selected_as_best = best_rank is None or candidate_rank > best_rank
        if selected_as_best:
            best_document = document
            best_report = candidate_report
            best_rank = candidate_rank
        result.attempts.append(
            _attempt_record(
                candidate_report,
                attempt=len(result.attempts),
                selected_as_best=selected_as_best,
                repeated_state=repeated_state,
            )
        )
        if candidate_report["overall_status"] == "pass":
            return result

        # Continue from the best public-validator state. A later regression is
        # audited above but cannot overwrite a better submission merely
        # because the fixed repair budget ended there.
        if not selected_as_best and best_document is not None:
            _write_ir_and_compile(workspace, submission_dir, best_document)

    if best_document is not None:
        _write_ir_and_compile(workspace, submission_dir, best_document)
        result.status = "completed"
        result.error = None
    return result


RUNNERS = {
    "m0": run_m0,
    "m1": run_m1,
    "m2": run_m2,
}
