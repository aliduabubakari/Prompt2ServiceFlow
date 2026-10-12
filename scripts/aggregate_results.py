#!/usr/bin/env python3
"""Aggregate an immutable experiment batch into the E1/E3 result tables.

The publication path consumes an explicit batch summary. Legacy run-directory
scans are available only through an opt-in latest-run mode and reject duplicate
experimental cells by default. The report emits:

- E1 primary table: per method — grounding, node/edge F1, binding accuracy,
  per-gate pass rates, full pass, tokens/cost.
- E3 first-failing-gate matrix: counts of first failing gate per method.
- Per-instance detail rows.

Usage:
    python scripts/aggregate_results.py \
      --batch-summary experiments/runs/<batch>.json --md
    python scripts/aggregate_results.py \
      --runs-root experiments/runs --allow-latest --model local-gpt-oss-20b
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATES = ["G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec"]
METHOD_ORDER = ["m0", "m1", "m2", "m3", "m4", "m5"]
DIRECT_APPLICABLE_GATES = {"G0", "G1", "G2", "G5"}


def _collect(
    runs_root: Path,
    model: str | None,
    *,
    batch_summary: Path | None = None,
    allow_latest: bool = False,
) -> list[tuple[Path, dict]]:
    """Collect an immutable declared batch, or explicitly opt into legacy latest-run mode."""

    paths: list[Path] = []
    if batch_summary is not None:
        document = json.loads(batch_summary.read_text(encoding="utf-8"))
        if document.get("status") not in {"complete", "complete_with_invalid_observations"}:
            raise ValueError(
                f"batch summary is not complete (status={document.get('status')!r}): "
                f"{batch_summary}"
            )
        expected_count = document.get("expected_cell_count")
        if expected_count is not None and len(document.get("runs", [])) != expected_count:
            raise ValueError(
                f"batch declares {expected_count} cells but lists "
                f"{len(document.get('runs', []))} runs"
            )
        expected_cells = document.get("expected_cells")
        if expected_cells is not None:
            identity_fields = (
                "model",
                "method",
                "split",
                "instance",
                "sample_index",
                "ablation",
            )
            expected_identities = {
                tuple(item.get(field) for field in identity_fields) for item in expected_cells
            }
            recorded_identities = {
                tuple(item.get(field) for field in identity_fields)
                for item in document.get("runs", [])
            }
            if expected_identities != recorded_identities:
                raise ValueError(
                    "recorded runs do not exactly cover the batch's declared expected cells"
                )
        for item in document.get("runs", []):
            raw = item.get("manifest_path")
            if not raw:
                raise ValueError(f"batch summary run lacks manifest_path: {item.get('run_id')}")
            path = Path(raw)
            if not path.is_absolute():
                path = (batch_summary.parent / path).resolve()
            if not path.is_file():
                raise ValueError(f"batch manifest is missing: {path}")
            paths.append(path)
    else:
        paths = list(runs_root.rglob("manifest.json"))

    collected: list[tuple[Path, dict]] = []
    for manifest_path in paths:
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            raise ValueError(f"invalid manifest JSON: {manifest_path}")
        model_id = manifest.get("model", {}).get("model_id")
        if (
            not manifest.get("method", {}).get("id")
            or not manifest.get("instance", {}).get("id")
            or not model_id
        ):
            raise ValueError(f"manifest lacks method/instance/model identity: {manifest_path}")
        if model and model_id != model:
            continue
        collected.append((manifest_path, manifest))

    cell_keys = [
        (
            manifest["model"]["model_id"],
            manifest["method"]["id"],
            manifest["instance"].get("split"),
            manifest["instance"]["id"],
            int(manifest.get("sample_index", 0)),
            (manifest.get("ablation") or {}).get("id", "primary"),
        )
        for _, manifest in collected
    ]
    if batch_summary is not None and len(cell_keys) != len(set(cell_keys)):
        raise ValueError("immutable batch contains duplicate experimental cells")

    if batch_summary is None:
        groups: dict[tuple[str, str, str, int], list[tuple[Path, dict]]] = defaultdict(list)
        for item in collected:
            path, manifest = item
            key = (
                manifest["method"]["id"],
                manifest["instance"]["id"],
                manifest["model"]["model_id"],
                int(manifest.get("sample_index", 0)),
            )
            groups[key].append(item)
        duplicates = {key: items for key, items in groups.items() if len(items) > 1}
        if duplicates and not allow_latest:
            raise ValueError(
                f"found {len(duplicates)} duplicate method/instance/model/sample cells; "
                "pass --batch-summary for a frozen batch (recommended) or --allow-latest for legacy smoke data"
            )
        if allow_latest:
            collected = [
                max(items, key=lambda item: item[0].stat().st_mtime) for items in groups.values()
            ]
    return collected


def _run_row(manifest: dict, manifest_path: Path | None = None) -> dict:
    evaluation = manifest.get("evaluation", {})
    usage = manifest.get("usage", {})
    reasoning_tokens = usage.get("reasoning_tokens")
    if reasoning_tokens is None and usage.get("per_stage"):
        reasoning_tokens = sum(
            int((stage.get("usage") or {}).get("reasoning_tokens", 0))
            for stage in usage["per_stage"]
        )
    row: dict = {
        "status": manifest.get("method_status") or manifest.get("stopping_reason"),
        "method": manifest.get("method", {}).get("id"),
        "model": manifest.get("model", {}).get("model_id"),
        "instance": manifest.get("instance", {}).get("id"),
        "split": manifest.get("instance", {}).get("split"),
        "sample_index": int(manifest.get("sample_index", 0)),
        "condition": (manifest.get("ablation") or {}).get("id", "primary"),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "tokens": usage.get("total_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": reasoning_tokens,
        "llm_calls": usage.get("llm_calls"),
        "latency_s": usage.get("latency_s"),
        "validator_calls": usage.get("validator_calls"),
        "evaluation_validator_calls": usage.get("evaluation_validator_calls"),
        "cost_usd": usage.get("cost_usd"),
        "llm_completion_count": len(usage.get("per_stage", [])),
        "length_truncated_calls": sum(
            str(stage.get("finish_reason", "")).lower() in {"length", "max_tokens"}
            for stage in usage.get("per_stage", [])
        ),
        "agent_steps": manifest.get("agent_steps"),
        "tool_calls": manifest.get("tool_calls"),
        "controller_continuations": manifest.get("controller_continuations"),
    }
    repair_attempts = evaluation.get("repair_attempts") or []
    repair_calls = sum(
        str(item.get("stage", "")).startswith("m4_repair") for item in usage.get("per_stage", [])
    )
    row.update(
        repair_initial_failure=(
            bool(repair_attempts) and repair_attempts[0].get("overall_status") == "fail"
        ),
        repair_calls=repair_calls,
        repair_public_success=(
            bool(repair_attempts)
            and (evaluation.get("validation") or {}).get("overall_status") == "pass"
        ),
        repair_improved_candidates=sum(
            item.get("selected_as_best") is True
            for index, item in enumerate(repair_attempts)
            if index > 0
        ),
        repair_rejected_candidates=sum(
            item.get("selected_as_best") is False and not bool(item.get("synthetic"))
            for index, item in enumerate(repair_attempts)
            if index > 0
        ),
        repair_repeated_states=sum(
            bool(item.get("repeated_state")) for item in repair_attempts
        ),
    )
    if "score_summary" in evaluation:
        summary = evaluation["score_summary"]
        row.update(
            full_pass=summary.get("full_pass_g0_g6"),
            first_failing_gate=summary.get("first_failing_gate"),
            node_f1=summary.get("node_f1"),
            edge_f1=summary.get("edge_f1"),
            wiring_f1=summary.get("wiring_f1"),
            wiring_applicable=(
                summary.get("wiring_applicable")
                if "wiring_applicable" in summary
                else summary.get("wiring_f1") is not None
            ),
            binding=summary.get("binding_top1_accuracy"),
            binding_version=summary.get("binding_version_accuracy"),
            alignment_edit_distance=summary.get("alignment_edit_distance"),
            over_decomposition_rate=summary.get("over_decomposition_rate"),
            under_decomposition_rate=summary.get("under_decomposition_rate"),
            source_step_coverage=summary.get("source_step_coverage"),
            gate_statuses=(evaluation.get("validation") or {}).get("gate_statuses", {}),
        )
    elif "direct_score" in evaluation:
        score = evaluation["direct_score"]
        row.update(
            full_pass=None,
            first_failing_gate=next(
                (gate for gate in GATES if score.get("gate_statuses", {}).get(gate) == "fail"),
                None,
            ),
            node_f1=score.get("node_f1"),
            edge_f1=score.get("edge_f1"),
            binding=None,
            grounded=score.get("service_grounded"),
            service_precision=score.get("service_precision"),
            service_recall=score.get("service_recall"),
            gate_statuses=score.get("gate_statuses", {}),
        )
    else:
        first_failure = "G0" if row["status"] == "parse_error" else None
        if row["status"] in {"llm_error", "timeout", "error"}:
            first_failure = "METHOD_ERROR"
        elif evaluation.get("error"):
            first_failure = "EVALUATION_ERROR"
        row.update(full_pass=None, first_failing_gate=first_failure, gate_statuses={})
    return row


def _bootstrap_mean_ci(values: list[float], *, iterations: int = 2000) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(20260817)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(iterations))
    return [means[int(0.025 * iterations)], means[min(iterations - 1, int(0.975 * iterations))]]


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _mean_present(entries: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in entries if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _sum_present(entries: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in entries if row.get(key) is not None]
    return sum(values) if values else None


def _exact_mcnemar(left: list[bool], right: list[bool]) -> dict:
    left_only = sum(a and not b for a, b in zip(left, right))
    right_only = sum(b and not a for a, b in zip(left, right))
    discordant = left_only + right_only
    if not discordant:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, i) for i in range(0, min(left_only, right_only) + 1))
        p_value = min(1.0, 2.0 * tail / (2**discordant))
    return {
        "left_only": left_only,
        "right_only": right_only,
        "discordant": discordant,
        "p_value": p_value,
    }


def _paired_bootstrap_difference(left: list[float], right: list[float]) -> dict:
    differences = [b - a for a, b in zip(left, right)]
    ci = _bootstrap_mean_ci(differences)
    mean = sum(differences) / len(differences) if differences else 0.0
    if len(differences) > 1:
        variance = sum((value - mean) ** 2 for value in differences) / (len(differences) - 1)
        standardized = mean / math.sqrt(variance) if variance > 0 else None
    else:
        standardized = None
    return {
        "mean_difference_right_minus_left": mean,
        "bootstrap_95ci": ci,
        "paired_standardized_effect_dz": standardized,
    }


def _paired_condition_comparisons(
    left_rows: list[dict], right_rows: list[dict], label: str
) -> list[dict]:
    def unit(row: dict) -> tuple[str, str, str, int]:
        return (row["model"], row["split"], row["instance"], row["sample_index"])

    left_index = {unit(row): row for row in left_rows}
    right_index = {unit(row): row for row in right_rows}
    keys = sorted(set(left_index) & set(right_index))
    results: list[dict] = []
    binary_keys = [
        key
        for key in keys
        if left_index[key].get("full_pass") is not None
        and right_index[key].get("full_pass") is not None
    ]
    if binary_keys:
        results.append(
            {
                "comparison": label,
                "metric": "full_pass",
                "paired_n": len(binary_keys),
                "exact_mcnemar": _exact_mcnemar(
                    [bool(left_index[key]["full_pass"]) for key in binary_keys],
                    [bool(right_index[key]["full_pass"]) for key in binary_keys],
                ),
            }
        )
    for metric in ("node_f1", "edge_f1", "wiring_f1", "binding"):
        metric_keys = [
            key
            for key in keys
            if left_index[key].get(metric) is not None and right_index[key].get(metric) is not None
        ]
        if metric_keys:
            results.append(
                {
                    "comparison": label,
                    "metric": metric,
                    "paired_n": len(metric_keys),
                    "paired_bootstrap": _paired_bootstrap_difference(
                        [float(left_index[key][metric]) for key in metric_keys],
                        [float(right_index[key][metric]) for key in metric_keys],
                    ),
                }
            )
    return results


def _summarize(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    per_method: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        per_method[row["method"]].append(row)
    e1_rows: list[dict] = []
    e3_rows: list[dict] = []
    for method in METHOD_ORDER:
        entries = per_method.get(method)
        if not entries:
            continue
        n = len(entries)
        scored = [row for row in entries if row.get("node_f1") is not None]
        gate_pass: dict[str, float] = {}
        gate_pass_ci: dict[str, list[float] | None] = {}
        cumulative_survival: dict[str, float | None] = {gate: None for gate in GATES}
        cumulative_survival_ci: dict[str, list[float] | None] = {gate: None for gate in GATES}
        applicable_sequence = ["G0", "G1", "G2", "G5"] if method in {"m0", "m1", "m2"} else GATES
        for gate in GATES:
            gate_applies = method not in {"m0", "m1", "m2"} or gate in DIRECT_APPLICABLE_GATES
            applicable = entries if gate_applies else []
            gate_pass[gate] = (
                sum(1 for row in applicable if row.get("gate_statuses", {}).get(gate) == "pass")
                / len(applicable)
                if applicable
                else None
            )
            gate_pass_ci[gate] = (
                _bootstrap_mean_ci(
                    [float(row.get("gate_statuses", {}).get(gate) == "pass") for row in applicable]
                )
                if applicable
                else None
            )
        survived = [True] * n
        for gate in applicable_sequence:
            survived = [
                prior and row.get("gate_statuses", {}).get(gate) == "pass"
                for prior, row in zip(survived, entries)
            ]
            values = [float(value) for value in survived]
            cumulative_survival[gate] = sum(values) / n
            cumulative_survival_ci[gate] = _bootstrap_mean_ci(values)
        full_applies = method in {"m3", "m4", "m5"}
        node_unconditional = [float(row.get("node_f1") or 0.0) for row in entries]
        edge_unconditional = [float(row.get("edge_f1") or 0.0) for row in entries]
        wiring_entries = [row for row in entries if row.get("wiring_applicable") is True]
        wiring_unconditional = [float(row.get("wiring_f1") or 0.0) for row in wiring_entries]
        full_values = [float(bool(row.get("full_pass"))) for row in entries] if full_applies else []
        token_values = [float(row["tokens"]) for row in entries if row.get("tokens") is not None]
        latency_values = [
            float(row["latency_s"]) for row in entries if row.get("latency_s") is not None
        ]
        total_cost = _sum_present(entries, "cost_usd")
        full_passes = sum(full_values)
        e1_rows.append(
            {
                "method": method,
                "runs": n,
                "parse_errors": sum(1 for row in entries if row["status"] == "parse_error"),
                "method_errors": sum(
                    1 for row in entries if row["status"] in {"llm_error", "timeout", "error"}
                ),
                "grounded_rate": (
                    sum(bool(row.get("grounded")) for row in entries) / n
                    if method in {"m0", "m1", "m2"}
                    else None
                ),
                "node_f1": (sum(node_unconditional) / n),
                "node_f1_conditional": (
                    sum(row["node_f1"] for row in scored) / len(scored) if scored else None
                ),
                "node_f1_95ci": _bootstrap_mean_ci(node_unconditional),
                "edge_f1": (sum(edge_unconditional) / n),
                "edge_f1_conditional": (
                    sum(row["edge_f1"] for row in scored if row["edge_f1"] is not None)
                    / sum(1 for row in scored if row["edge_f1"] is not None)
                    if any(row.get("edge_f1") is not None for row in scored)
                    else None
                ),
                "edge_f1_95ci": _bootstrap_mean_ci(edge_unconditional),
                "wiring_f1": (
                    sum(wiring_unconditional) / len(wiring_unconditional)
                    if method in {"m3", "m4", "m5"} and wiring_unconditional
                    else None
                ),
                "wiring_f1_95ci": (
                    _bootstrap_mean_ci(wiring_unconditional)
                    if method in {"m3", "m4", "m5"}
                    else None
                ),
                "wiring_applicable_runs": (
                    len(wiring_unconditional) if method in {"m3", "m4", "m5"} else None
                ),
                "binding_top1": (
                    sum(float(row.get("binding") or 0.0) for row in entries) / n
                    if method in {"m3", "m4", "m5"}
                    else None
                ),
                "binding_top1_95ci": (
                    _bootstrap_mean_ci([float(row.get("binding") or 0.0) for row in entries])
                    if method in {"m3", "m4", "m5"}
                    else None
                ),
                "binding_version_accuracy": (
                    sum(float(row.get("binding_version") or 0.0) for row in entries) / n
                    if method in {"m3", "m4", "m5"}
                    else None
                ),
                "gate_pass_rates": gate_pass,
                "gate_pass_95ci": gate_pass_ci,
                "cumulative_gate_survival": cumulative_survival,
                "cumulative_gate_survival_95ci": cumulative_survival_ci,
                "full_pass_rate": (sum(full_values) / n if full_applies else None),
                "full_pass_95ci": (_bootstrap_mean_ci(full_values) if full_applies else None),
                "mean_tokens": (
                    sum(token_values) / len(token_values) if token_values else None
                ),
                "median_tokens": _percentile(token_values, 0.50),
                "p95_tokens": _percentile(token_values, 0.95),
                "total_tokens": _sum_present(entries, "tokens"),
                "mean_prompt_tokens": _mean_present(entries, "prompt_tokens"),
                "total_prompt_tokens": _sum_present(entries, "prompt_tokens"),
                "mean_completion_tokens": _mean_present(entries, "completion_tokens"),
                "total_completion_tokens": _sum_present(entries, "completion_tokens"),
                "mean_reasoning_tokens": _mean_present(entries, "reasoning_tokens"),
                "total_reasoning_tokens": _sum_present(entries, "reasoning_tokens"),
                "mean_llm_calls": _mean_present(entries, "llm_calls"),
                "mean_latency_s": _mean_present(entries, "latency_s"),
                "p95_latency_s": _percentile(latency_values, 0.95),
                "mean_validator_calls": _mean_present(entries, "validator_calls"),
                "mean_evaluation_validator_calls": _mean_present(
                    entries, "evaluation_validator_calls"
                ),
                "mean_agent_steps": _mean_present(entries, "agent_steps"),
                "mean_tool_calls": _mean_present(entries, "tool_calls"),
                "mean_controller_continuations": _mean_present(
                    entries, "controller_continuations"
                ),
                "length_truncated_calls": sum(
                    int(row.get("length_truncated_calls", 0)) for row in entries
                ),
                "length_truncated_runs": sum(
                    int(row.get("length_truncated_calls", 0) > 0) for row in entries
                ),
                "length_truncated_run_rate": (
                    sum(int(row.get("length_truncated_calls", 0) > 0) for row in entries) / n
                ),
                "missing_token_records": sum(row["tokens"] is None for row in entries),
                "total_cost_usd": total_cost,
                "mean_cost_usd": (total_cost / n if total_cost is not None else None),
                "cost_per_full_pass_usd": (
                    total_cost / full_passes
                    if total_cost is not None and full_applies and full_passes
                    else None
                ),
                "repair_initial_failures": sum(
                    bool(row.get("repair_initial_failure")) for row in entries
                ),
                "repair_success_rate": (
                    sum(
                        bool(row.get("repair_public_success"))
                        for row in entries
                        if row.get("repair_initial_failure")
                    )
                    / sum(bool(row.get("repair_initial_failure")) for row in entries)
                    if any(row.get("repair_initial_failure") for row in entries)
                    else None
                ),
                "mean_repair_calls": (
                    sum(int(row.get("repair_calls", 0)) for row in entries) / n
                    if method == "m4"
                    else None
                ),
                "repair_improved_candidates": (
                    sum(int(row.get("repair_improved_candidates", 0)) for row in entries)
                    if method == "m4"
                    else None
                ),
                "repair_rejected_candidates": (
                    sum(int(row.get("repair_rejected_candidates", 0)) for row in entries)
                    if method == "m4"
                    else None
                ),
                "repair_repeated_states": (
                    sum(int(row.get("repair_repeated_states", 0)) for row in entries)
                    if method == "m4"
                    else None
                ),
            }
        )
        first_fails = Counter(
            row["first_failing_gate"] for row in entries if row.get("first_failing_gate")
        )
        e3_rows.append({"method": method, "first_failing_gate_counts": dict(first_fails)})
    return e1_rows, e3_rows


def aggregate(
    runs_root: Path,
    model: str | None = None,
    *,
    batch_summary: Path | None = None,
    allow_latest: bool = False,
    benchmark_root: Path = PROJECT_ROOT / "benchmark",
) -> dict:
    infrastructure_attempts: list[dict] = []
    preflight_failures: list[dict] = []
    if batch_summary is not None:
        batch_document = json.loads(batch_summary.read_text(encoding="utf-8"))
        infrastructure_attempts = list(batch_document.get("invalid_attempts", []))
        preflight_failures = list(batch_document.get("preflight_failures", []))
    declared = _collect(runs_root, model, batch_summary=batch_summary, allow_latest=allow_latest)
    invalid_collected = [
        (path, manifest) for path, manifest in declared if manifest.get("run_validity") == "invalid"
    ]
    collected = [
        (path, manifest) for path, manifest in declared if manifest.get("run_validity") != "invalid"
    ]
    rows = [_run_row(manifest, path) for path, manifest in collected]
    invalid_observations = [
        {
            "model": manifest["model"]["model_id"],
            "method": manifest["method"]["id"],
            "split": manifest["instance"].get("split"),
            "instance": manifest["instance"]["id"],
            "sample_index": int(manifest.get("sample_index", 0)),
            "run_id": manifest.get("run_id"),
            "failure_category": manifest.get(
                "failure_category", "unclassified_non_semantic_failure"
            ),
            "message": manifest.get("failure_message")
            or manifest.get("last_assistant_error")
            or manifest.get("stopping_reason"),
            "manifest_path": str(path),
        }
        for path, manifest in invalid_collected
    ]
    coverage_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for path, manifest in declared:
        coverage_groups[(manifest["model"]["model_id"], manifest["method"]["id"])].append(manifest)
    operational_coverage = []
    for (model_id, method), manifests in sorted(coverage_groups.items()):
        invalid = [item for item in manifests if item.get("run_validity") == "invalid"]
        categories = Counter(
            item.get("failure_category", "unclassified_non_semantic_failure") for item in invalid
        )
        operational_coverage.append(
            {
                "model": model_id,
                "method": method,
                "declared_cells": len(manifests),
                "valid_observations": len(manifests) - len(invalid),
                "invalid_observations": len(invalid),
                "coverage_rate": (len(manifests) - len(invalid)) / len(manifests),
                "failure_categories": dict(categories),
            }
        )
    conditions = sorted({row["condition"] for row in rows})
    if len(conditions) == 1:
        e1_rows, e3_rows = _summarize(rows)
    else:
        # Mixing interventions into one method mean is statistically invalid.
        # Multi-condition batches are exposed only through by_condition.
        e1_rows, e3_rows = [], []
    by_condition = {}
    for condition in conditions:
        condition_e1, condition_e3 = _summarize(
            [row for row in rows if row["condition"] == condition]
        )
        by_condition[condition] = {"e1": condition_e1, "e3": condition_e3}
    by_split = {}
    for split in sorted({row["split"] for row in rows if row["split"]}):
        split_rows = [row for row in rows if row["split"] == split]
        split_conditions = sorted({row["condition"] for row in split_rows})
        if len(split_conditions) == 1:
            split_e1, split_e3 = _summarize(split_rows)
        else:
            split_e1, split_e3 = [], []
        by_split[split] = {
            "e1": split_e1,
            "e3": split_e3,
            "by_condition": {
                condition: dict(
                    zip(
                        ("e1", "e3"),
                        _summarize([row for row in split_rows if row["condition"] == condition]),
                    )
                )
                for condition in split_conditions
            },
        }
    by_model = {}
    for model_id in sorted({row["model"] for row in rows if row["model"]}):
        model_e1, model_e3 = _summarize([row for row in rows if row["model"] == model_id])
        by_model[model_id] = {"e1": model_e1, "e3": model_e3}

    pass_at_k: list[dict] = []
    for condition in conditions:
        for method in METHOD_ORDER:
            method_rows = [
                row for row in rows if row["method"] == method and row["condition"] == condition
            ]
            grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
            for row in method_rows:
                grouped[(row["model"], row["split"], row["instance"])].append(row)
            applicable = [
                items
                for items in grouped.values()
                if any(r.get("full_pass") is not None for r in items)
            ]
            if applicable:
                maximum_k = min(len(items) for items in applicable)
                for k in range(1, maximum_k + 1):
                    estimates = []
                    for items in applicable:
                        n = len(items)
                        successes = sum(bool(row.get("full_pass")) for row in items)
                        estimate = (
                            1.0
                            if n - successes < k
                            else 1.0 - math.comb(n - successes, k) / math.comb(n, k)
                        )
                        estimates.append(estimate)
                    pass_at_k.append(
                        {
                            "condition": condition,
                            "method": method,
                            "instances": len(applicable),
                            "k": k,
                            "pass_at_k": sum(estimates) / len(estimates),
                            "bootstrap_95ci": _bootstrap_mean_ci(estimates),
                        }
                    )

    comparisons: list[dict] = []
    comparison_rows = rows if len(conditions) == 1 else []
    row_index = {
        (
            row["method"],
            row["model"],
            row["split"],
            row["instance"],
            row["sample_index"],
        ): row
        for row in comparison_rows
    }
    for left, right in (("m3", "m4"), ("m4", "m5")):
        keys = sorted(
            set(key[1:] for key in row_index if key[0] == left)
            & set(key[1:] for key in row_index if key[0] == right)
        )
        binary_keys = [
            key
            for key in keys
            if row_index[(left, *key)].get("full_pass") is not None
            and row_index[(right, *key)].get("full_pass") is not None
        ]
        if binary_keys:
            left_values = [bool(row_index[(left, *key)]["full_pass"]) for key in binary_keys]
            right_values = [bool(row_index[(right, *key)]["full_pass"]) for key in binary_keys]
            comparisons.append(
                {
                    "comparison": f"{left}_vs_{right}",
                    "metric": "full_pass",
                    "paired_n": len(binary_keys),
                    "exact_mcnemar": _exact_mcnemar(left_values, right_values),
                }
            )
        for metric in ("node_f1", "edge_f1", "wiring_f1", "binding"):
            metric_keys = [
                key
                for key in keys
                if row_index[(left, *key)].get(metric) is not None
                and row_index[(right, *key)].get(metric) is not None
            ]
            if metric_keys:
                comparisons.append(
                    {
                        "comparison": f"{left}_vs_{right}",
                        "metric": metric,
                        "paired_n": len(metric_keys),
                        "paired_bootstrap": _paired_bootstrap_difference(
                            [float(row_index[(left, *key)][metric]) for key in metric_keys],
                            [float(row_index[(right, *key)][metric]) for key in metric_keys],
                        ),
                    }
                )

    condition_comparisons: list[dict] = []
    if len(conditions) > 1:
        for condition in conditions:
            if condition.startswith("baseline_"):
                continue
            condition_rows = [row for row in rows if row["condition"] == condition]
            methods = {row["method"] for row in condition_rows}
            if len(methods) != 1:
                continue
            method = next(iter(methods))
            baseline = f"baseline_{method}"
            baseline_rows = [row for row in rows if row["condition"] == baseline]
            if method == "m5" and not baseline_rows:
                baseline = "a13_validator_budget_4"
                if condition == baseline:
                    continue
                baseline_rows = [row for row in rows if row["condition"] == baseline]
            if baseline_rows:
                condition_comparisons.extend(
                    _paired_condition_comparisons(
                        baseline_rows,
                        condition_rows,
                        f"{baseline}_vs_{condition}",
                    )
                )

    distractor_confusion: dict[str, Counter] = defaultdict(Counter)
    for path, manifest in collected:
        method = manifest["method"]["id"]
        condition = (manifest.get("ablation") or {}).get("id", "primary")
        confusion_key = f"{condition}/{method}"
        evaluation = manifest.get("evaluation", {})
        if "direct_score" in evaluation:
            distractor_confusion[confusion_key].update(
                evaluation["direct_score"].get("distractor_confusion", {})
            )
            continue
        score_path = path.parent / "score.json"
        if score_path.is_file():
            score = json.loads(score_path.read_text(encoding="utf-8"))
            distractor_confusion[confusion_key].update(
                score.get("binding", {}).get("confusion_by_label", {})
            )

    inventory: dict[str, dict[str, str]] = {}
    inventory_dir = benchmark_root / "source" / "zenodo_v1_0_0" / "inventories"
    for inventory_path in inventory_dir.glob("*_pipeline_inventory.csv"):
        with inventory_path.open(encoding="utf-8", newline="") as handle:
            for item in csv.DictReader(handle):
                normalized = re.sub(r"[^a-z0-9]+", "_", item["pipeline_id"].lower()).strip("_")
                inventory[normalized] = item
    metadata: dict[str, dict] = {}
    for split in ("main", "validation", "extension"):
        for instance_dir in (benchmark_root / "instances" / split).glob("*"):
            gold_path = instance_dir / "gold" / "serviceflow.yaml"
            if not gold_path.is_file():
                continue
            import yaml

            gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
            requirement = gold.get("requirement", {})
            item = inventory.get(instance_dir.name, {})
            metadata[instance_dir.name] = {
                "split": split,
                "complexity": (item.get("complexity_label") or "unknown").lower().replace(" ", "_"),
                "topology": str(requirement.get("topology", "unknown")),
                "information_sufficiency": str(
                    requirement.get("information_sufficiency", "unknown")
                ),
                "source_type": item.get("source_type") or "unknown",
                "schedule_type": str((gold.get("schedule") or {}).get("type", "unknown")),
                "catalog_categories": sorted(
                    {
                        str(intent.get("category", "unknown"))
                        for intent in gold.get("service_intents", [])
                    }
                ),
            }
    stratified: dict[str, dict[str, list[dict]]] = {}
    for dimension in (
        "complexity",
        "topology",
        "information_sufficiency",
        "source_type",
        "schedule_type",
    ):
        stratified[dimension] = {}
        values = sorted(
            {metadata.get(row["instance"], {}).get(dimension, "unknown") for row in rows}
        )
        for value in values:
            selected_rows = [
                row
                for row in rows
                if metadata.get(row["instance"], {}).get(dimension, "unknown") == value
            ]
            summary_rows, _ = _summarize(selected_rows)
            stratified[dimension][value] = summary_rows
    stratified["catalog_category"] = {}
    categories = sorted(
        {category for item in metadata.values() for category in item.get("catalog_categories", [])}
    )
    for category in categories:
        selected_rows = [
            row
            for row in rows
            if category in metadata.get(row["instance"], {}).get("catalog_categories", [])
        ]
        summary_rows, _ = _summarize(selected_rows)
        stratified["catalog_category"][category] = summary_rows
    conservative_end_to_end_full_pass = []
    for method in ("m3", "m4", "m5"):
        declared_count = sum(manifest["method"]["id"] == method for _, manifest in declared)
        if not declared_count:
            continue
        method_rows = [row for row in rows if row["method"] == method]
        full_passes = sum(bool(row.get("full_pass")) for row in method_rows)
        conservative_end_to_end_full_pass.append(
            {
                "method": method,
                "declared_cells": declared_count,
                "valid_observations": len(method_rows),
                "invalid_observations": declared_count - len(method_rows),
                "full_passes": full_passes,
                "full_pass_rate": full_passes / declared_count,
            }
        )
    return {
        "runs_root": str(runs_root),
        "batch_summary": str(batch_summary) if batch_summary else None,
        "model_filter": model,
        "declared_run_count": len(declared),
        "run_count": len(rows),
        "invalid_observation_count": len(invalid_observations),
        "invalid_observations": invalid_observations,
        "infrastructure_attempts": infrastructure_attempts,
        "preflight_failures": preflight_failures,
        "operational_coverage": operational_coverage,
        "conservative_end_to_end_full_pass": conservative_end_to_end_full_pass,
        "e1": e1_rows,
        "e3": e3_rows,
        "by_split": by_split,
        "by_model": by_model,
        "by_condition": by_condition,
        "pass_at_k": pass_at_k,
        "paired_comparisons": comparisons,
        "condition_comparisons": condition_comparisons,
        "distractor_confusion": {
            method: dict(counter) for method, counter in sorted(distractor_confusion.items())
        },
        "stratified": stratified,
        "per_run": {
            f"{row['model']}/{row['condition']}/{row['method']}/{row['split']}/"
            f"{row['instance']}/sample_{row['sample_index']}": row
            for row in rows
        },
    }


def _fmt(value, digits=2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_ci(value, interval) -> str:
    if value is None:
        return "-"
    if not interval:
        return _fmt(value)
    return f"{_fmt(value)} [{_fmt(interval[0])}, {_fmt(interval[1])}]"


def _append_e1_table(lines: list[str], rows: list[dict]) -> None:
    lines += [
        "| method | runs | parse_err | grounded | node F1 [95% CI] | "
        "edge F1 [95% CI] | wiring F1 | wiring n | bind@1 | "
        + " | ".join(GATES)
        + " | full pass [95% CI] | mean tokens | total cost (USD) |",
        "|" + "---|" * (12 + len(GATES)),
    ]
    for row in rows:
        gates = " | ".join(_fmt(row["gate_pass_rates"].get(g)) for g in GATES)
        lines.append(
            f"| {row['method']} | {row['runs']} | {row['parse_errors']} "
            f"| {_fmt(row['grounded_rate'])} "
            f"| {_fmt_ci(row['node_f1'], row['node_f1_95ci'])} "
            f"| {_fmt_ci(row['edge_f1'], row['edge_f1_95ci'])} "
            f"| {_fmt(row['wiring_f1'])} | {_fmt(row.get('wiring_applicable_runs'), 0)} "
            f"| {_fmt(row['binding_top1'])} | {gates} "
            f"| {_fmt_ci(row['full_pass_rate'], row['full_pass_95ci'])} "
            f"| {_fmt(row['mean_tokens'], 0)} | {_fmt(row['total_cost_usd'], 4)} |"
        )


def _append_efficiency_table(lines: list[str], rows: list[dict]) -> None:
    lines += [
        "| method | runs | prompt tok (total) | completion tok (total) | reasoning tok (total) | "
        "tokens/run mean | p50 | p95 | LLM calls/run | latency/run s | latency p95 s | "
        "validator calls/run | truncated calls | truncated runs | cost/run USD | total cost USD | cost/full pass USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['runs']} "
            f"| {_fmt(row.get('total_prompt_tokens'), 0)} "
            f"| {_fmt(row.get('total_completion_tokens'), 0)} "
            f"| {_fmt(row.get('total_reasoning_tokens'), 0)} "
            f"| {_fmt(row.get('mean_tokens'), 0)} "
            f"| {_fmt(row.get('median_tokens'), 0)} "
            f"| {_fmt(row.get('p95_tokens'), 0)} "
            f"| {_fmt(row.get('mean_llm_calls'))} "
            f"| {_fmt(row.get('mean_latency_s'))} "
            f"| {_fmt(row.get('p95_latency_s'))} "
            f"| {_fmt(row.get('mean_validator_calls'))} "
            f"| {_fmt(row.get('length_truncated_calls'), 0)} "
            f"| {_fmt(row.get('length_truncated_runs'), 0)} "
            f"| {_fmt(row.get('mean_cost_usd'), 4)} "
            f"| {_fmt(row.get('total_cost_usd'), 4)} "
            f"| {_fmt(row.get('cost_per_full_pass_usd'), 4)} |"
        )


def _append_repair_table(lines: list[str], rows: list[dict]) -> None:
    repair_rows = [row for row in rows if row["method"] == "m4"]
    if not repair_rows:
        return
    lines += [
        "| method | runs | initial failures | public recoveries | repair success | calls/run | improved candidates | rejected candidates | repeated states |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in repair_rows:
        recoveries = (
            round(row["repair_initial_failures"] * row["repair_success_rate"])
            if row.get("repair_success_rate") is not None
            else None
        )
        lines.append(
            f"| {row['method']} | {row['runs']} "
            f"| {row['repair_initial_failures']} | {_fmt(recoveries, 0)} "
            f"| {_fmt(row.get('repair_success_rate'))} "
            f"| {_fmt(row.get('mean_repair_calls'))} "
            f"| {_fmt(row.get('repair_improved_candidates'), 0)} "
            f"| {_fmt(row.get('repair_rejected_candidates'), 0)} "
            f"| {_fmt(row.get('repair_repeated_states'), 0)} |"
        )


def _append_agentic_table(lines: list[str], rows: list[dict]) -> None:
    agentic_rows = [row for row in rows if row["method"] == "m5"]
    if not agentic_rows:
        return
    lines += [
        "| method | runs | agent steps/run | tool calls/run | controller continuations/run | validator calls/run |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in agentic_rows:
        lines.append(
            f"| {row['method']} | {row['runs']} "
            f"| {_fmt(row.get('mean_agent_steps'))} "
            f"| {_fmt(row.get('mean_tool_calls'))} "
            f"| {_fmt(row.get('mean_controller_continuations'))} "
            f"| {_fmt(row.get('mean_validator_calls'))} |"
        )


def to_markdown(report: dict) -> str:
    multi_model = len(report.get("by_model", {})) > 1
    lines = [
        f"# Aggregate results ({report.get('declared_run_count', report['run_count'])} declared cells, "
        f"{report['run_count']} valid observations, model: {report['model_filter'] or 'all'})",
        "",
        (
            "## E1 descriptive pooled semantic results (valid observations)"
            if multi_model
            else "## E1 semantic results (valid observations)"
        ),
        "",
    ]
    if multi_model:
        lines += [
            "This table pools model conditions descriptively. Use the by-model tables and paired comparisons for model-aware inference.",
            "",
        ]
    if report["e1"]:
        _append_e1_table(lines, report["e1"])
    else:
        lines.append("Multi-condition batch; pooled means are intentionally suppressed.")
        for condition, payload in report["by_condition"].items():
            lines += ["", f"### {condition}", ""]
            _append_e1_table(lines, payload["e1"])
    if multi_model:
        lines += ["", "## E1 semantic results by model", ""]
        for model_id, payload in report["by_model"].items():
            lines += [f"### {model_id}", ""]
            _append_e1_table(lines, payload["e1"])
            lines.append("")
    lines += [
        "",
        "## Efficiency and cost (valid observations)",
        "",
        "Reasoning tokens are a subset of completion tokens when the provider reports them.",
        "",
    ]
    if report["e1"]:
        _append_efficiency_table(lines, report["e1"])
    else:
        lines.append("Multi-condition batch; pooled efficiency means are intentionally suppressed.")
        for condition, payload in report["by_condition"].items():
            lines += ["", f"### {condition}", ""]
            _append_efficiency_table(lines, payload["e1"])
    if multi_model:
        lines += ["", "## Efficiency and cost by model", ""]
        for model_id, payload in report["by_model"].items():
            lines += [f"### {model_id}", ""]
            _append_efficiency_table(lines, payload["e1"])
            lines.append("")
    lines += ["", "## M4 repair-controller outcomes", ""]
    _append_repair_table(lines, report["e1"])
    if any(row.get("method") == "m5" for row in report["e1"]):
        lines += ["", "## M5 agentic-controller outcomes", ""]
        _append_agentic_table(lines, report["e1"])
    if multi_model:
        for model_id, payload in report["by_model"].items():
            lines += ["", f"### {model_id}", ""]
            _append_repair_table(lines, payload["e1"])
    lines += ["", "## E3 first-failing-gate counts", ""]
    for row in report["e3"]:
        lines.append(f"- **{row['method']}**: {row['first_failing_gate_counts'] or '{}'}")
    lines += ["", "## Operational coverage and compatibility", ""]
    lines += [
        "| model | method | declared | valid | invalid | coverage | failure categories |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report.get("operational_coverage", []):
        lines.append(
            f"| {row['model']} | {row['method']} | {row['declared_cells']} "
            f"| {row['valid_observations']} | {row['invalid_observations']} "
            f"| {_fmt(row['coverage_rate'])} | {row['failure_categories'] or '{}'} |"
        )
    lines += ["", "## Conservative end-to-end full pass", ""]
    lines += [
        "Invalid observations count as non-passes in this sensitivity view.",
        "",
        "| method | declared | valid | invalid | full passes | full-pass rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report.get("conservative_end_to_end_full_pass", []):
        lines.append(
            f"| {row['method']} | {row['declared_cells']} | {row['valid_observations']} "
            f"| {row['invalid_observations']} | {row['full_passes']} "
            f"| {_fmt(row['full_pass_rate'])} |"
        )
    if report.get("invalid_observations"):
        lines += ["", "### Invalid observation details", ""]
        for item in report["invalid_observations"]:
            lines.append(
                f"- `{item['model']}/{item['method']}/{item['split']}/{item['instance']}`: "
                f"`{item['failure_category']}` — {item['message']}"
            )
    if report.get("infrastructure_attempts") or report.get("preflight_failures"):
        lines += ["", "## Retried infrastructure attempts", ""]
        lines.append(
            "These attempts were excluded from experimental cells; their cells were rerun."
        )
        for item in report.get("preflight_failures", []):
            lines.append(
                f"- `{item['model']}/preflight`: `{item['failure_category']}` — "
                f"{item.get('message') or '(no message)'}"
            )
        for item in report.get("infrastructure_attempts", []):
            lines.append(
                f"- `{item['model']}/{item['method']}/{item['split']}/{item['instance']}`: "
                f"`{item['failure_category']}` — {item.get('message') or '(no message)'}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "experiments" / "runs")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--batch-summary",
        type=Path,
        default=None,
        help="immutable batch summary produced by run_experiment.py (recommended)",
    )
    parser.add_argument(
        "--allow-latest",
        action="store_true",
        help="legacy smoke-data mode: choose latest duplicate by file mtime",
    )
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=PROJECT_ROOT / "benchmark",
    )
    parser.add_argument("--md", action="store_true", help="print markdown instead of JSON")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    try:
        report = aggregate(
            args.runs_root,
            args.model,
            batch_summary=args.batch_summary,
            allow_latest=args.allow_latest,
            benchmark_root=args.benchmark_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = to_markdown(report) if args.md else json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
