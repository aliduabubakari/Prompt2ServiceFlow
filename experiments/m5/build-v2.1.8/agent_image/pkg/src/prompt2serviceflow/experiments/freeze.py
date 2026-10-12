"""Experiment-freeze loading and fail-closed consistency checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from prompt2serviceflow.experiments import prompts
from prompt2serviceflow.experiments.methods import DEFAULT_REPAIR_BUDGET, METHOD_IDS
from prompt2serviceflow.experiments.harness import HARNESS_VERSION
from prompt2serviceflow.experiments.runtime_compiler import RUNTIME_COMPILER_VERSION


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FREEZE_PATH = REPO_ROOT / "experiments" / "config" / "freeze.json"
DEFAULT_ROSTER_PATH = REPO_ROOT / "experiments" / "config" / "models.json"


class FreezeError(RuntimeError):
    """Raised when a run does not match the declared experiment freeze."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_freeze(path: Path = DEFAULT_FREEZE_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise FreezeError(f"freeze file is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"freeze file cannot be read: {exc}") from exc
    if not document.get("freeze_id"):
        raise FreezeError("freeze file lacks freeze_id")
    return document


def check_freeze(
    *,
    freeze_path: Path = DEFAULT_FREEZE_PATH,
    roster_path: Path = DEFAULT_ROSTER_PATH,
    repair_budget: int = DEFAULT_REPAIR_BUDGET,
    model_id: str | None = None,
    require_frozen: bool = True,
    include_m5: bool = False,
    max_workers: int | None = None,
) -> tuple[dict[str, Any], list[str]]:
    freeze = load_freeze(freeze_path)
    errors: list[str] = []
    if require_frozen and freeze.get("status") != "frozen":
        errors.append(f"freeze status is {freeze.get('status')!r}, expected 'frozen'")
    if freeze.get("prompt_version") != prompts.PROMPT_VERSION:
        errors.append(
            f"prompt version drift: freeze={freeze.get('prompt_version')!r}, "
            f"code={prompts.PROMPT_VERSION!r}"
        )
    if freeze.get("runtime_compiler_version") != RUNTIME_COMPILER_VERSION:
        errors.append(
            "runtime compiler version drift: "
            f"freeze={freeze.get('runtime_compiler_version')!r}, "
            f"code={RUNTIME_COMPILER_VERSION!r}"
        )
    if freeze.get("harness_version") != HARNESS_VERSION:
        errors.append(
            f"harness version drift: freeze={freeze.get('harness_version')!r}, "
            f"code={HARNESS_VERSION!r}"
        )
    if freeze.get("repair_budget") != repair_budget:
        errors.append(
            f"repair budget drift: freeze={freeze.get('repair_budget')!r}, run={repair_budget}"
        )
    if tuple(freeze.get("primary_methods", ())) != METHOD_IDS:
        errors.append(
            f"primary method set drift: freeze={freeze.get('primary_methods')!r}, "
            f"code={list(METHOD_IDS)!r}"
        )
    expected_roster = freeze.get("roster_sha256")
    actual_roster = sha256_file(roster_path) if roster_path.is_file() else None
    if expected_roster != actual_roster:
        errors.append(f"model roster drift: freeze={expected_roster!r}, actual={actual_roster!r}")
    if model_id is not None and model_id not in freeze.get("model_roster", []):
        errors.append(f"model {model_id!r} is not in the frozen model_roster")
    try:
        roster_document = json.loads(roster_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        roster_document = {"models": {}}
        errors.append(f"model roster cannot be parsed: {exc}")
    roster_models = roster_document.get("models", {})
    if set(freeze.get("model_roster", [])) != set(roster_models):
        errors.append("frozen model_roster does not exactly match configured roster keys")
    decoding = freeze.get("decoding") or {}
    endpoint = freeze.get("endpoint") or {}
    for configured_id, spec in roster_models.items():
        if spec.get("temperature", 0.0) != decoding.get("temperature"):
            errors.append(f"{configured_id}: temperature differs from freeze")
        if spec.get("top_p") != decoding.get("top_p"):
            errors.append(f"{configured_id}: top_p differs from freeze")
        if spec.get("max_tokens", 8000) != decoding.get("max_tokens"):
            errors.append(f"{configured_id}: max_tokens differs from freeze")
        frozen_context = decoding.get("context_window")
        if frozen_context == "per_model":
            artifact_context = (
                (freeze.get("model_artifacts") or {}).get(configured_id) or {}
            ).get("maximum_context_length")
            if spec.get("context_window", 100_000) != artifact_context:
                errors.append(f"{configured_id}: context_window differs from model artifact")
        elif spec.get("context_window", 100_000) != frozen_context:
            errors.append(f"{configured_id}: context_window differs from freeze")
        if spec.get("base_url") != endpoint.get("base_url"):
            errors.append(f"{configured_id}: endpoint differs from freeze")
    if freeze.get("validator_budget_derivation") != "repair_budget + 1":
        errors.append("validator-budget derivation differs from protocol")
    if freeze.get("m4_execution_feedback") is not True:
        errors.append("M4 execution feedback is not enabled in freeze")
    retrieval = freeze.get("retrieval") or {}
    if not retrieval.get("embedding_model"):
        errors.append("retrieval embedding model is not frozen")
    if not isinstance(retrieval.get("top_k"), int) or retrieval.get("top_k", 0) < 1:
        errors.append("retrieval top_k must be a positive integer")
    if (
        not isinstance(retrieval.get("hybrid_reciprocal_rank_constant"), int)
        or retrieval.get("hybrid_reciprocal_rank_constant", 0) < 1
    ):
        errors.append("hybrid reciprocal-rank constant must be a positive integer")
    if (
        not isinstance(freeze.get("samples_per_instance"), int)
        or freeze["samples_per_instance"] < 1
    ):
        errors.append("samples_per_instance must be a positive integer")
    if (
        "pilot_samples_per_instance" in freeze
        and (
            not isinstance(freeze.get("pilot_samples_per_instance"), int)
            or freeze["pilot_samples_per_instance"] < 1
        )
    ):
        errors.append("pilot_samples_per_instance must be a positive integer")
    if (
        not isinstance(freeze.get("robustness_samples_per_instance"), int)
        or freeze["robustness_samples_per_instance"] < 1
    ):
        errors.append("robustness_samples_per_instance must be a positive integer")
    sample_seeds = decoding.get("sample_seeds")
    robustness_samples = freeze.get("robustness_samples_per_instance")
    if sample_seeds is not None and (
        not isinstance(sample_seeds, list)
        or len(sample_seeds) < (robustness_samples or 0)
        or any(not isinstance(value, int) for value in sample_seeds)
        or len(sample_seeds) != len(set(sample_seeds))
    ):
        errors.append(
            "decoding.sample_seeds must contain unique integer seeds for every robustness sample"
        )
    elif sample_seeds:
        for configured_id, spec in roster_models.items():
            if spec.get("seed") != sample_seeds[0]:
                errors.append(f"{configured_id}: configured seed differs from first sample seed")
    execution = freeze.get("execution") or {}
    frozen_workers = execution.get("max_workers")
    if frozen_workers is not None and (
        not isinstance(frozen_workers, int) or isinstance(frozen_workers, bool) or frozen_workers < 1
    ):
        errors.append("execution.max_workers must be a positive integer")
    if max_workers is not None and frozen_workers is not None and max_workers != frozen_workers:
        errors.append(
            f"parallel worker drift: freeze={frozen_workers!r}, run={max_workers!r}"
        )
    model_blocks = execution.get("model_blocks")
    if model_blocks is not None:
        valid_blocks = (
            isinstance(model_blocks, list)
            and bool(model_blocks)
            and all(
                isinstance(block, list)
                and bool(block)
                and all(isinstance(model, str) and model for model in block)
                and len(block) == len(set(block))
                for block in model_blocks
            )
        )
        if not valid_blocks:
            errors.append("execution.model_blocks must be a non-empty list of unique model lists")
        elif [model for block in model_blocks for model in block] != list(
            freeze.get("model_roster", [])
        ):
            errors.append(
                "execution.model_blocks must partition the frozen roster in exact order"
            )
    if include_m5:
        from prompt2serviceflow.experiments.agentic import (
            DEFAULT_M5_AGENT_STEPS,
            DEFAULT_M5_IDLE_CONTINUATIONS,
            DEFAULT_M5_TIMEOUT_SECONDS,
            DEFAULT_M5_TOKEN_CAP,
            M5_AGENT_CONTEXT_POLICY,
            M5_PROMPT_VERSION,
            M5_VERSION,
        )

        m5 = freeze.get("m5") or {}
        if m5.get("token_cap_default") != DEFAULT_M5_TOKEN_CAP:
            errors.append("M5 token-cap default differs from freeze")
        if m5.get("timeout_s_default") != DEFAULT_M5_TIMEOUT_SECONDS:
            errors.append("M5 timeout default differs from freeze")
        if m5.get("image_version") != M5_VERSION:
            errors.append("M5 image version differs from freeze")
        if m5.get("prompt_version") != M5_PROMPT_VERSION:
            errors.append("M5 prompt version differs from freeze")
        if m5.get("max_idle_continuations") != DEFAULT_M5_IDLE_CONTINUATIONS:
            errors.append("M5 idle-continuation limit differs from freeze")
        if m5.get("agent_step_budget") != DEFAULT_M5_AGENT_STEPS:
            errors.append("M5 agent-step budget differs from freeze")
        if m5.get("agent_context_policy") != M5_AGENT_CONTEXT_POLICY:
            errors.append("M5 agent context policy differs from freeze")
        if m5.get("validator_budget") != repair_budget + 1:
            errors.append("M5 validator-call budget is not matched to M4")
        if m5.get("validator_budget_derivation") != "repair_budget + 1":
            errors.append("M5 validator-budget derivation differs from protocol")
    if (freeze.get("decoding") or {}).get("parallel_predictions") != 1:
        errors.append("local model parallel_predictions must be frozen at 1")
    if include_m5 and "a13" in freeze:
        a13 = freeze.get("a13") or {}
        if a13.get("model") not in freeze.get("model_roster", []):
            errors.append("A13 model is not in the frozen roster")
        budgets = a13.get("validator_budgets")
        if (
            not isinstance(budgets, list)
            or not budgets
            or any(not isinstance(value, int) or value < 1 for value in budgets)
            or DEFAULT_REPAIR_BUDGET + 1 not in budgets
        ):
            errors.append("A13 validator budgets must be positive and include the matched budget")
        subset = a13.get("main_subset")
        if not isinstance(subset, list) or not subset or len(subset) != len(set(subset)):
            errors.append("A13 Main subset must be a non-empty unique list")
    return freeze, errors


def require_matching_freeze(**kwargs: Any) -> dict[str, Any]:
    freeze, errors = check_freeze(**kwargs)
    if errors:
        raise FreezeError("; ".join(errors))
    return freeze
