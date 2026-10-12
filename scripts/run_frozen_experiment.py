#!/usr/bin/env python3
"""Run or resume a declared frozen experiment method set.

This is the publication runner. It validates the freeze and leakage gate once,
executes a deterministic cell order, persists the master batch after every
cell, and creates the one-shot Validation-20 lock only after all requested
cells finish. A freeze may declare M0-M4 or the controlled M0-M5 comparison.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from prompt2serviceflow.experiments import prompts  # noqa: E402
from prompt2serviceflow.experiments.freeze import check_freeze  # noqa: E402
from prompt2serviceflow.experiments.harness import HARNESS_VERSION, run_one  # noqa: E402
from prompt2serviceflow.experiments.leakage import scan_workspace, scan_workspace_root  # noqa: E402
from prompt2serviceflow.experiments.llm import (  # noqa: E402
    OpenAICompatibleClient,
    UsageLedger,
    load_model_configs,
)
from prompt2serviceflow.experiments.methods import (  # noqa: E402
    METHOD_IDS,
    validator_budget_for,
)
from prompt2serviceflow.experiments.runtime_compiler import (  # noqa: E402
    RUNTIME_COMPILER_VERSION,
)


PRIMARY_METHODS = METHOD_IDS
SUPPORTED_METHODS = (*PRIMARY_METHODS, "m5")
TERMINAL_RUN_STATUSES = {"recorded", "recorded_invalid"}


def _m5_version() -> str:
    from prompt2serviceflow.experiments.agentic import M5_VERSION

    return M5_VERSION


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _cell_key(item: dict) -> tuple[str, str, str, str, int]:
    return (
        item["model"],
        item["method"],
        item["split"],
        item["instance"],
        int(item["sample_index"]),
    )


def _infrastructure_error_text(manifest: dict) -> str:
    """Collect the error surfaces used by primary and exploratory methods."""

    return "\n".join(
        str(value)
        for value in (
            manifest.get("method_error"),
            manifest.get("last_assistant_error"),
            manifest.get("failure_message"),
        )
        if value
    )


def _classify_infrastructure_failure(manifest: dict) -> str | None:
    """Return a non-semantic failure category, or ``None`` for model output failures."""

    error = _infrastructure_error_text(manifest).lower()
    if (
        "error rendering prompt with jinja template" in error
        or "conversation roles must alternate" in error
    ):
        return "provider_prompt_template_incompatibility"
    if any(
        marker in error
        for marker in (
            "lm link",
            "no models loaded",
            "failed to load model",
            "connection closed",
            "connection refused",
            "server disconnected",
            "remote protocol error",
        )
    ):
        return "model_serving_connectivity"
    if any(
        marker in error
        for marker in (
            "proxy token budget exhausted",
            '"type":"budget"',
            '"type": "budget"',
            "rate limit",
            "too many requests",
            "429:",
        )
    ):
        return "provider_rate_or_token_budget"
    if any(
        marker in error
        for marker in (
            "invalid api key",
            "authentication",
            "unauthorized",
            "401:",
            "401 ",
        )
    ):
        return "provider_authentication"
    if any(
        marker in error
        for marker in (
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "internal server error",
            "500:",
            "502:",
            "503:",
            "504:",
        )
    ):
        return "provider_service_failure"
    if "timed out" in error or "timeout" in error:
        return "provider_timeout"
    if str(manifest.get("stopping_reason", "")).startswith("agent_exit_"):
        return "agent_container_failure"
    return None


def _classify_invalid_m5_failure(manifest: dict) -> str:
    """Backward-compatible M5 classifier with a generic infrastructure fallback."""

    return _classify_infrastructure_failure(manifest) or "inference_or_container_infrastructure"


def _record_invalid_attempt(
    *,
    summary: dict,
    run_dir: Path,
    cell: tuple[str, str, str, str, int],
    category: str,
    message: str,
) -> dict:
    """Audit an infrastructure attempt while leaving its experimental cell pending."""

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_validity"] = "invalid"
    manifest["failure_category"] = category
    manifest["failure_message"] = message
    manifest["result_inclusion"] = "operational_coverage_only"
    _write_json(manifest_path, manifest)

    model, method, split, instance, sample_index = cell
    attempt = {
        "model": model,
        "method": method,
        "split": split,
        "instance": instance,
        "sample_index": sample_index,
        "run_id": manifest["run_id"],
        "manifest_path": str(manifest_path.resolve()),
        "failure_category": category,
        "message": message,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    summary.setdefault("invalid_attempts", []).append(attempt)
    return attempt


def _record_invalid_m5(
    *,
    summary: dict,
    run_dir: Path,
    cell: tuple[str, str, str, str, int],
    message: str,
) -> dict:
    """Persist an invalid M5 observation without treating it as a semantic result."""

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    category = _classify_invalid_m5_failure(manifest)
    manifest["run_validity"] = "invalid"
    manifest["failure_category"] = category
    manifest["failure_message"] = message
    manifest["result_inclusion"] = "operational_coverage_only"
    _write_json(manifest_path, manifest)

    model, method, split, instance, sample_index = cell
    record = {
        "status": "recorded_invalid",
        "model": model,
        "method": method,
        "split": split,
        "instance": instance,
        "sample_index": sample_index,
        "run_id": manifest["run_id"],
        "manifest_path": str(manifest_path.resolve()),
        "failure_category": category,
        "message": message,
    }
    summary.setdefault("invalid_observations", []).append(
        {key: value for key, value in record.items() if key not in {"status", "manifest_path"}}
    )
    return record


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="*", default=None, help="default: frozen roster")
    parser.add_argument(
        "--methods",
        default=",".join(PRIMARY_METHODS),
        help="comma-separated methods (primary default: m0,m1,m2,m3,m4; m5 is exploratory)",
    )
    parser.add_argument(
        "--split",
        choices=("main", "validation", "extension", "all", "corpus"),
        default="main",
        help="all preserves Main+Validation; corpus selects Main+Validation+Extension",
    )
    parser.add_argument("--instances", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--samples", type=int, default=None, help="default: freeze value")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="bounded concurrent M0-M4 cells within each model block (default: 1)",
    )
    parser.add_argument("--repair-budget", type=int, default=3)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "experiments/config/models.json"
    )
    parser.add_argument(
        "--freeze-config",
        type=Path,
        default=PROJECT_ROOT / "experiments/config/freeze.json",
        help="experiment freeze/candidate document paired with --config",
    )
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "experiments/runs")
    parser.add_argument(
        "--workspaces-root", type=Path, default=PROJECT_ROOT / "experiments/workspaces"
    )
    parser.add_argument("--benchmark-root", type=Path, default=PROJECT_ROOT / "benchmark")
    parser.add_argument("--batch-summary", type=Path, default=None, help="resume this master batch")
    parser.add_argument("--allow-unfrozen", action="store_true", help="smoke/development only")
    parser.add_argument("--allow-validation-rerun", action="store_true")
    parser.add_argument("--skip-image-build", action="store_true")
    parser.add_argument(
        "--auto-load-model",
        action="store_true",
        help="run `lms load <model_name>` before each model block",
    )
    return parser.parse_args()


def _select_instances(args: argparse.Namespace) -> list[tuple[str, Path, Path]]:
    splits = (
        ("main", "validation", "extension")
        if args.split == "corpus"
        else ("main", "validation")
        if args.split == "all"
        else (args.split,)
    )
    selected: list[tuple[str, Path, Path]] = []
    for split in splits:
        for workspace in sorted((args.workspaces_root / split).glob("*")):
            if not (workspace / "workspace.yaml").is_file():
                continue
            if args.instances and workspace.name not in args.instances:
                continue
            instance = args.benchmark_root / "instances" / split / workspace.name
            if instance.is_dir():
                selected.append((split, workspace, instance))
    if args.limit is not None:
        selected = selected[: args.limit]
    if args.instances:
        found = {workspace.name for _, workspace, _ in selected}
        missing = sorted(set(args.instances) - found)
        if missing:
            raise ValueError(f"requested instances not found: {missing}")
    if not selected:
        raise ValueError("no instances selected")
    return selected


def _probe_model(config) -> str:
    client = OpenAICompatibleClient(config, UsageLedger(), max_retries=1)
    result = client.complete(
        stage="publication_preflight",
        system="Reply exactly with OK.",
        user="OK",
    )
    if result.text.strip() != "OK":
        raise RuntimeError(
            f"model {config.model_id} failed the exact preflight response: {result.text.strip()!r}"
        )
    return result.model


def _probe_agentic_prompt_template(config) -> str:
    """Exercise the multi-turn tool shape used by M5, not just one-shot chat."""

    client = OpenAICompatibleClient(config, UsageLedger(), max_retries=0)
    result = client._client.chat.completions.create(
        model=config.model_name,
        messages=[
            {"role": "system", "content": "You are a tool-using compatibility probe."},
            {"role": "user", "content": "Acknowledge the supplied tool result."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "p2sf_probe_call",
                        "type": "function",
                        "function": {"name": "p2sf_probe", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "p2sf_probe_call", "content": "OK"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "p2sf_probe",
                    "description": "M5 prompt-template compatibility probe",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        max_tokens=16,
        temperature=0,
    )
    return str(result.model)


def _sample_seeds(freeze: dict, samples: int, configured_seed: int | None) -> list[int | None]:
    """Resolve the predeclared seed for each repeated observation."""

    declared = (freeze.get("decoding") or {}).get("sample_seeds")
    if declared is not None:
        if len(declared) < samples:
            raise ValueError(
                f"freeze declares {len(declared)} sample seeds but {samples} samples were requested"
            )
        return [int(seed) for seed in declared[:samples]]
    if samples == 1:
        return [configured_seed]
    base = 0 if configured_seed is None else configured_seed
    return [base + index for index in range(samples)]


def _publication_model_selection_allowed(freeze: dict, model_ids: list[str]) -> bool:
    """Allow the full roster or one explicitly frozen sequential model block."""

    roster = list(freeze.get("model_roster", []))
    if model_ids == roster:
        return True
    blocks = (freeze.get("execution") or {}).get("model_blocks") or []
    return model_ids in blocks


def _publication_methods(freeze: dict) -> tuple[str, ...]:
    """Return the method set declared for publication by this freeze."""

    return tuple(freeze.get("compared_methods") or freeze.get("primary_methods") or ())


def _resume_mismatches(
    summary: dict,
    *,
    freeze_id: str,
    model_ids: list[str],
    methods: tuple[str, ...],
    split: str,
    samples: int,
    selected: list[tuple[str, Path, Path]],
    sample_seeds: list[int | None] | None = None,
    max_workers: int | None = None,
) -> list[str]:
    expected_instances = [
        {"split": item_split, "id": workspace.name} for item_split, workspace, _ in selected
    ]
    expected = {
        "freeze_id": freeze_id,
        "prompt_version": prompts.PROMPT_VERSION,
        "harness_version": HARNESS_VERSION,
        "runtime_compiler_version": RUNTIME_COMPILER_VERSION,
        "models": model_ids,
        "methods": list(methods),
        "split": split,
        "samples_per_instance": samples,
        "instances": expected_instances,
    }
    if "m5" in methods:
        expected["m5_image_version"] = _m5_version()
    if sample_seeds is not None:
        expected["sample_seeds"] = sample_seeds
    if max_workers is not None:
        expected["max_workers"] = max_workers
    return [
        f"{key}: batch={summary.get(key)!r}, requested={value!r}"
        for key, value in expected.items()
        if summary.get(key) != value
    ]


def main() -> int:
    args = _args()
    load_dotenv(PROJECT_ROOT / ".env")
    roster = load_model_configs(args.config)
    methods = tuple(item.strip() for item in args.methods.split(",") if item.strip())
    unknown = sorted(set(methods) - set(SUPPORTED_METHODS))
    if unknown:
        print(f"error: unknown methods: {unknown}", file=sys.stderr)
        return 2
    if args.max_workers < 1:
        print("error: --max-workers must be at least 1", file=sys.stderr)
        return 2
    if args.max_workers > 1 and ("m5" in methods or args.auto_load_model):
        print(
            "error: parallel workers are supported only for M0-M4 without --auto-load-model",
            file=sys.stderr,
        )
        return 2

    freeze, freeze_errors = check_freeze(
        freeze_path=args.freeze_config,
        roster_path=args.config,
        repair_budget=args.repair_budget,
        require_frozen=not args.allow_unfrozen,
        include_m5="m5" in methods,
        max_workers=args.max_workers,
    )
    if freeze_errors and not args.allow_unfrozen:
        print(f"error: freeze mismatch: {'; '.join(freeze_errors)}", file=sys.stderr)
        return 1
    model_ids = args.models or list(freeze.get("model_roster", []))
    missing_models = sorted(set(model_ids) - set(roster))
    if missing_models:
        print(f"error: models absent from roster: {missing_models}", file=sys.stderr)
        return 2
    samples = args.samples or int(freeze.get("samples_per_instance", 1))
    if samples < 1:
        print("error: samples must be at least 1", file=sys.stderr)
        return 2
    registered_sample_counts = {
        int(freeze.get("pilot_samples_per_instance", 1)),
        int(freeze.get("samples_per_instance", 1)),
        int(freeze.get("robustness_samples_per_instance", 3)),
    }
    if samples not in registered_sample_counts:
        print(
            f"error: samples={samples} is not a registered primary/robustness count "
            f"{sorted(registered_sample_counts)}",
            file=sys.stderr,
        )
        return 2
    try:
        seed_schedule = _sample_seeds(freeze, samples, roster[model_ids[0]].seed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not args.allow_unfrozen:
        publication_errors = []
        publication_methods = _publication_methods(freeze)
        if methods != publication_methods:
            publication_errors.append(f"publication methods must be {publication_methods!r}")
        if not _publication_model_selection_allowed(freeze, model_ids):
            publication_errors.append(
                "models must be the full frozen roster or one explicitly frozen model block"
            )
        if args.instances or args.limit is not None:
            publication_errors.append("instance subsets/limits are smoke-only")
        if publication_errors:
            print(
                "error: frozen publication batch is incomplete: " + "; ".join(publication_errors),
                file=sys.stderr,
            )
            return 2

    try:
        selected = _select_instances(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.allow_unfrozen:
        # A development/smoke batch can only expose selected workspaces, so
        # scanning those is complete for its threat boundary and avoids a
        # long 60-workspace preflight before every one-instance iteration.
        selected_workspaces = [workspace for _, workspace, _ in selected]
        print(
            f"preflight: scanning {len(selected_workspaces)} selected workspace(s) "
            "for leakage...",
            flush=True,
        )
        findings = [
            finding
            for workspace in selected_workspaces
            for finding in scan_workspace(workspace)
        ]
        leakage = {
            "status": "pass" if not findings else "fail",
            "finding_count": len(findings),
            "workspaces_scanned": len(selected_workspaces),
        }
    else:
        print(
            f"preflight: scanning all submission workspaces under {args.workspaces_root} "
            "for leakage...",
            flush=True,
        )
        leakage = scan_workspace_root(args.workspaces_root)
    if leakage["status"] != "pass":
        print(f"error: leakage gate found {leakage['finding_count']} issues", file=sys.stderr)
        return 1
    print(
        f"preflight: leakage gate passed ({leakage['workspaces_scanned']} workspaces)",
        flush=True,
    )

    validation_lock = args.runs_root / "validation_lock.json"
    includes_validation = args.split in {"validation", "all", "corpus"}
    if includes_validation and validation_lock.exists() and not args.allow_validation_rerun:
        print(f"error: Validation-20 is locked by {validation_lock}", file=sys.stderr)
        return 1

    if args.batch_summary:
        summary_path = args.batch_summary.resolve()
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot resume batch summary: {exc}", file=sys.stderr)
            return 2
        mismatches = _resume_mismatches(
            summary,
            freeze_id=freeze["freeze_id"],
            model_ids=model_ids,
            methods=methods,
            split=args.split,
            samples=samples,
            selected=selected,
            sample_seeds=seed_schedule,
            max_workers=args.max_workers,
        )
        if mismatches:
            print(
                "error: resume arguments do not match the immutable batch design: "
                + "; ".join(mismatches),
                file=sys.stderr,
            )
            return 2
        batch_id = summary["batch_id"]
    else:
        batch_id = (
            f"frozen__{freeze['freeze_id']}__"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__{uuid.uuid4().hex[:8]}"
        )
        summary_path = args.runs_root / f"{batch_id}.json"
        summary = {
            "batch_id": batch_id,
            "freeze_id": freeze["freeze_id"],
            "freeze_status": freeze.get("status"),
            "prompt_version": prompts.PROMPT_VERSION,
            "harness_version": HARNESS_VERSION,
            "runtime_compiler_version": RUNTIME_COMPILER_VERSION,
            "freeze_errors_ignored": freeze_errors if args.allow_unfrozen else [],
            "models": model_ids,
            "methods": list(methods),
            "split": args.split,
            "instances": [
                {"split": split, "id": workspace.name} for split, workspace, _ in selected
            ],
            "samples_per_instance": samples,
            "sample_seeds": seed_schedule,
            "max_workers": args.max_workers,
            "parallelism": {
                "scope": "within_model_block",
                "scheduling": "bounded_deterministic_waves",
                "workers": args.max_workers,
            },
            "invalid_observation_policy": {
                "action": "audit_attempt_and_stop_for_resume",
                "semantic_result_inclusion": "exclude",
                "operational_coverage_inclusion": "include",
                "experimental_cell_state": "pending_until_valid_attempt",
            },
            "expected_cells": [
                {
                    "model": model_id,
                    "method": method,
                    "split": split,
                    "instance": workspace.name,
                    "sample_index": sample_index,
                }
                for model_id in model_ids
                for split, workspace, _ in selected
                for sample_index in range(samples)
                for method in methods
            ],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "runs": [],
        }
        if "m5" in methods:
            summary["m5_image_version"] = _m5_version()
        _write_json(summary_path, summary)

    summary.setdefault(
        "invalid_observation_policy",
        {
            "action": "audit_attempt_and_stop_for_resume",
            "semantic_result_inclusion": "exclude",
            "operational_coverage_inclusion": "include",
            "experimental_cell_state": "pending_until_valid_attempt",
        },
    )
    completed_cells = {
        _cell_key(item)
        for item in summary.get("runs", [])
        if item.get("status") in TERMINAL_RUN_STATUSES
    }
    # Older runner versions stopped at the first invalid M5 observation and
    # stored it only in last_infrastructure_failure. Adopt that already-written
    # forensic manifest on resume instead of spending another full agent run
    # reproducing the same provider/container failure.
    previous_failure = summary.get("last_infrastructure_failure")
    if previous_failure and summary.get("status") != "interrupted_infrastructure":
        previous_cell = _cell_key(previous_failure)
        previous_run_dir = args.runs_root / previous_failure["run_id"]
        previous_manifest = previous_run_dir / "manifest.json"
        if previous_cell not in completed_cells and previous_manifest.is_file():
            record = _record_invalid_m5(
                summary=summary,
                run_dir=previous_run_dir,
                cell=previous_cell,
                message=previous_failure["message"],
            )
            summary["runs"].append(record)
            completed_cells.add(previous_cell)
            summary["last_recorded_invalid_observation"] = previous_failure
            summary.pop("last_infrastructure_failure", None)
            _write_json(summary_path, summary)
            print(
                "recorded invalid observation "
                f"{record['failure_category']} for {previous_cell}; continuing"
            )
    m5_image_ready = args.skip_image_build or any(
        item.get("method") == "m5" and item.get("status") in TERMINAL_RUN_STATUSES
        for item in summary.get("runs", [])
    )
    for model_id in model_ids:
        model_cells = {
            (model_id, method, split, workspace.name, sample_index)
            for split, workspace, _ in selected
            for sample_index in range(samples)
            for method in methods
        }
        if model_cells <= completed_cells:
            print(f"skipping completed model block {model_id}")
            continue
        config = roster[model_id]
        if args.auto_load_model:
            # Publication models run sequentially. Keeping the prior model
            # resident can exhaust remote unified memory and turn a valid
            # cell into an LM Link disconnect, so make the switch explicit.
            subprocess.run(["lms", "unload", "--all"], check=True, timeout=300)
            subprocess.run(
                [
                    "lms",
                    "load",
                    config.model_name,
                    "--context-length",
                    str(config.context_window),
                    "--parallel",
                    "1",
                    "--identifier",
                    config.model_name,
                    "--yes",
                ],
                check=True,
                timeout=900,
            )
        try:
            resolved_model = _probe_model(config)
        except Exception as exc:
            category = _classify_infrastructure_failure({"method_error": str(exc)})
            category = category or "model_preflight_failure"
            failure = {
                "model": model_id,
                "failure_category": category,
                "message": str(exc),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            summary.setdefault("preflight_failures", []).append(failure)
            summary["status"] = "interrupted_infrastructure"
            summary["last_infrastructure_failure"] = failure
            _write_json(summary_path, summary)
            print(
                f"error: model preflight failed for {model_id}: {exc}",
                file=sys.stderr,
            )
            print(
                "restore the model service and resume with "
                f"--batch-summary {summary_path.resolve()}",
                file=sys.stderr,
            )
            return 1
        summary.setdefault("resolved_models", {})[model_id] = resolved_model
        if "m5" in methods:
            try:
                agentic_model = _probe_agentic_prompt_template(config)
            except Exception as exc:
                summary.setdefault("agentic_prompt_template_preflight", {})[model_id] = {
                    "status": "fail",
                    "error": str(exc),
                }
                summary["status"] = "interrupted_infrastructure"
                _write_json(summary_path, summary)
                print(
                    f"error: {model_id} failed the M5 tool-conversation preflight: {exc}",
                    file=sys.stderr,
                )
                print(
                    "resolve provider tool-conversation compatibility and resume with "
                    f"--batch-summary {summary_path.resolve()}",
                    file=sys.stderr,
                )
                return 1
            else:
                summary.setdefault("agentic_prompt_template_preflight", {})[model_id] = {
                    "status": "pass",
                    "resolved_model": agentic_model,
                }
        _write_json(summary_path, summary)
        pending = [
            (model_id, method, split, workspace.name, sample_index, workspace, instance)
            for split, workspace, instance in selected
            for sample_index in range(samples)
            for method in methods
            if (model_id, method, split, workspace.name, sample_index) not in completed_cells
        ]

        # M5 has shared image lifecycle state, so a batch containing M5 is
        # deliberately sequential. Iteration order interleaves the declared
        # methods within each instance/seed cell group.
        if "m5" in methods:
            from prompt2serviceflow.experiments.agentic import M5Error, run_m5

            for _, method, split, instance_id, sample_index, workspace, instance in pending:
                cell = (model_id, method, split, instance_id, sample_index)
                sample_config = replace(config, seed=seed_schedule[sample_index])
                if method == "m5":
                    run_id = (
                        f"m5__{split}__{instance_id}__{model_id}__s{sample_index}__"
                        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__{uuid.uuid4().hex[:8]}"
                    )
                    run_dir = args.runs_root / run_id
                    try:
                        manifest = run_m5(
                            workspace=workspace,
                            instance_dir=instance,
                            model=sample_config,
                            run_dir=run_dir,
                            validator_budget=validator_budget_for(args.repair_budget),
                            token_cap=int((freeze.get("m5") or {}).get("token_cap_default", 750000)),
                            timeout_s=int((freeze.get("m5") or {}).get("timeout_s_default", 1800)),
                            max_idle_continuations=int(
                                (freeze.get("m5") or {}).get("max_idle_continuations", 3)
                            ),
                            agent_step_budget=int(
                                (freeze.get("m5") or {}).get("agent_step_budget", 12)
                            ),
                            roster_path=args.config,
                            skip_image_build=m5_image_ready,
                            freeze_document=freeze,
                            freeze_errors_ignored=(freeze_errors if args.allow_unfrozen else []),
                            batch_id=batch_id,
                            sample_index=sample_index,
                        )
                    except M5Error as exc:
                        record = _record_invalid_m5(
                            summary=summary, run_dir=run_dir, cell=cell, message=str(exc)
                        )
                        summary["runs"].append(record)
                        completed_cells.add(cell)
                        _write_json(summary_path, summary)
                        print(
                            "recorded invalid observation "
                            f"{record['failure_category']} for {cell}: {exc}",
                            file=sys.stderr,
                        )
                        m5_image_ready = True
                        continue
                    m5_image_ready = True
                else:
                    manifest = run_one(
                        method,
                        workspace=workspace,
                        instance_dir=instance,
                        model=sample_config,
                        runs_root=args.runs_root,
                        repair_budget=args.repair_budget,
                        batch_id=batch_id,
                        sample_index=sample_index,
                        freeze_document=freeze,
                        roster_path=args.config,
                        freeze_path=args.freeze_config,
                    )
                    run_dir = args.runs_root / manifest["run_id"]
                    infrastructure_category = _classify_infrastructure_failure(manifest)
                    if infrastructure_category is not None:
                        message = _infrastructure_error_text(manifest) or (
                            "model-serving infrastructure failed"
                        )
                        attempt = _record_invalid_attempt(
                            summary=summary,
                            run_dir=run_dir,
                            cell=cell,
                            category=infrastructure_category,
                            message=message,
                        )
                        summary["status"] = "interrupted_infrastructure"
                        summary["last_infrastructure_failure"] = attempt
                        _write_json(summary_path, summary)
                        print(
                            f"error: infrastructure attempt recorded for {cell}: {message}",
                            file=sys.stderr,
                        )
                        return 1
                summary["runs"].append(
                    {
                        "status": "recorded",
                        "model": model_id,
                        "method": method,
                        "split": split,
                        "instance": instance_id,
                        "sample_index": sample_index,
                        "run_id": manifest["run_id"],
                        "manifest_path": str((run_dir / "manifest.json").resolve()),
                    }
                )
                completed_cells.add(cell)
                summary.pop("last_infrastructure_failure", None)
                _write_json(summary_path, summary)
                print(f"recorded {model_id} {method} {split}/{instance_id} sample={sample_index}")
            continue

        def execute_primary(item):
            _, method, _, _, sample_index, workspace, instance = item
            sample_config = replace(config, seed=seed_schedule[sample_index])
            manifest = run_one(
                method,
                workspace=workspace,
                instance_dir=instance,
                model=sample_config,
                runs_root=args.runs_root,
                repair_budget=args.repair_budget,
                batch_id=batch_id,
                sample_index=sample_index,
                freeze_document=freeze,
                roster_path=args.config,
                freeze_path=args.freeze_config,
            )
            return manifest, args.runs_root / manifest["run_id"]

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            for offset in range(0, len(pending), args.max_workers):
                wave = pending[offset : offset + args.max_workers]
                futures = [executor.submit(execute_primary, item) for item in wave]
                results = []
                for item, future in zip(wave, futures):
                    try:
                        results.append((item, future.result(), None))
                    except Exception as exc:
                        results.append((item, None, exc))

                wave_failed = False
                for item, result, worker_error in results:
                    _, method, split, instance_id, sample_index, _, _ = item
                    cell = (model_id, method, split, instance_id, sample_index)
                    if worker_error is not None:
                        failure = {
                            "model": model_id,
                            "method": method,
                            "split": split,
                            "instance": instance_id,
                            "sample_index": sample_index,
                            "failure_category": "runner_worker_failure",
                            "message": str(worker_error),
                            "recorded_at": datetime.now(timezone.utc).isoformat(),
                        }
                        summary.setdefault("worker_failures", []).append(failure)
                        summary["last_infrastructure_failure"] = failure
                        wave_failed = True
                        continue
                    manifest, run_dir = result
                    infrastructure_category = _classify_infrastructure_failure(manifest)
                    if infrastructure_category is not None:
                        message = _infrastructure_error_text(manifest) or (
                            "model-serving infrastructure failed"
                        )
                        attempt = _record_invalid_attempt(
                            summary=summary,
                            run_dir=run_dir,
                            cell=cell,
                            category=infrastructure_category,
                            message=message,
                        )
                        summary["last_infrastructure_failure"] = attempt
                        wave_failed = True
                        print(
                            f"error: infrastructure attempt recorded for {cell}: {message}",
                            file=sys.stderr,
                        )
                        continue
                    summary["runs"].append(
                        {
                            "status": "recorded",
                            "model": model_id,
                            "method": method,
                            "split": split,
                            "instance": instance_id,
                            "sample_index": sample_index,
                            "run_id": manifest["run_id"],
                            "manifest_path": str((run_dir / "manifest.json").resolve()),
                        }
                    )
                    completed_cells.add(cell)
                    print(f"recorded {model_id} {method} {split}/{instance_id} sample={sample_index}")
                _write_json(summary_path, summary)
                if wave_failed:
                    summary["status"] = "interrupted_infrastructure"
                    _write_json(summary_path, summary)
                    print(
                        "one or more cells remain pending; restore capacity and resume with "
                        f"--batch-summary {summary_path.resolve()}",
                        file=sys.stderr,
                    )
                    return 1
                summary.pop("last_infrastructure_failure", None)

    expected_cells = len(model_ids) * len(selected) * samples * len(methods)
    if len(completed_cells) != expected_cells:
        print(
            f"error: batch ended with {len(completed_cells)}/{expected_cells} unique cells",
            file=sys.stderr,
        )
        return 1
    summary["expected_cell_count"] = expected_cells
    invalid_count = sum(
        item.get("status") == "recorded_invalid" for item in summary.get("runs", [])
    )
    summary["recorded_cell_count"] = len(completed_cells)
    summary["valid_recorded_cell_count"] = len(completed_cells) - invalid_count
    summary["invalid_recorded_cell_count"] = invalid_count
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["status"] = "complete_with_invalid_observations" if invalid_count else "complete"
    _write_json(summary_path, summary)
    if includes_validation and not args.allow_unfrozen:
        _write_json(
            validation_lock,
            {
                "freeze_id": freeze["freeze_id"],
                "batch_id": batch_id,
                "batch_summary": str(summary_path),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    print(f"complete: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
