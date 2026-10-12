#!/usr/bin/env python3
"""Validate frozen publication batches and prepare the final evaluation data bundle.

The script treats the pipeline instance as the statistical unit. It first
averages the three seeded repetitions within each instance, then computes
macro means, 95% BCa bootstrap intervals, paired sign-flip tests, and Holm
adjustments. Direct-Argo methods retain only their explicitly applicable
outcomes; they are never assigned an end-to-end pass or failure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "experiments/analysis/evaluation_final"
PRIMARY_BATCHES = (
    ROOT
    / "experiments/runs/frozen__freeze-2026-10-01.sintef.v19__20261001T204646.947784Z__7da3753f.json",
    ROOT
    / "experiments/runs/qwen480-v21/frozen__freeze-2026-10-08.deepinfra.v21__20261008T100403.597052Z__486e18ae.json",
    ROOT
    / "experiments/runs/deepseek41-v22/frozen__freeze-2026-10-08.deepinfra.v22__20261008T100403.076491Z__f390947e.json",
)
ABLATION_BATCHES = (
    ROOT
    / "experiments/runs/ablation-qwen-v24/ablations__deepinfra-qwen3-coder-480b-turbo__20261010T195909.668288Z__69c9456f.json",
    ROOT
    / "experiments/runs/ablation-qwen-v24/ablations__deepinfra-qwen3-coder-480b-turbo__20261011T055725.548808Z__5e295670.json",
    ROOT
    / "experiments/runs/ablation-qwen-v24/ablations__deepinfra-qwen3-coder-480b-turbo__20261011T174944.582274Z__d06663f5.json",
)
POSTHOC_MAIN_G6 = DEFAULT_OUT / "posthoc_main_g6_assert.json"
METHODS = ("m0", "m1", "m2", "m3", "m4", "m5")
SERVICEFLOW_METHODS = {"m3", "m4", "m5"}
GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec")
COMMON_GATES = ("G0", "G1", "G2", "G5")
SPLIT_SIZES = {"main": 40, "validation": 20, "extension": 50}
SEEDS = (101, 202, 303)
ABLATIONS = (
    "a1_no_contracts",
    "a2_no_policies",
    "a3_no_g5_repair_feedback",
    "a5_no_repair",
    "a6_unstructured_diagnostics",
)
MODEL_LABELS = {
    "sintef-qwen3-8-27b-nvfp4": "Qwen3.8-27B (SINTEF)",
    "deepinfra-qwen3-coder-480b-turbo": "Qwen3-Coder-480B",
    "deepinfra-deepseek-v4-1-flash": "DeepSeek-V4.1-Flash",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _portable_path(value: str) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _resolve_manifest(batch_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repository_relative = (ROOT / path).resolve()
    if repository_relative.is_file():
        return repository_relative
    return (batch_path.parent / path).resolve()


def _cell_identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        item.get(key)
        for key in ("model", "method", "split", "instance", "sample_index", "ablation")
    )


def validate_batch(path: Path, *, ablation: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    batch = _read_json(path)
    errors: list[str] = []
    if batch.get("status") != "complete":
        errors.append(f"status={batch.get('status')!r}, expected 'complete'")
    expected = batch.get("expected_cells") or []
    runs = batch.get("runs") or []
    expected_count = int(batch.get("expected_cell_count", len(expected)))
    if len(expected) != expected_count:
        errors.append(f"expected-cell list has {len(expected)} entries, declared {expected_count}")
    if len(runs) != expected_count:
        errors.append(f"run list has {len(runs)} entries, declared {expected_count}")
    expected_ids = {_cell_identity(item) for item in expected}
    recorded_ids = {_cell_identity(item) for item in runs}
    if len(expected_ids) != len(expected):
        errors.append("expected-cell list contains duplicates")
    if len(recorded_ids) != len(runs):
        errors.append("recorded run list contains duplicate cells")
    if expected_ids != recorded_ids:
        errors.append("recorded cells do not exactly cover expected cells")

    manifests: list[dict[str, Any]] = []
    manifest_paths: list[Path] = []
    for item in runs:
        raw = item.get("manifest_path")
        if not raw:
            errors.append(f"run {item.get('run_id')} lacks manifest_path")
            continue
        manifest_path = _resolve_manifest(path, raw)
        if not manifest_path.is_file():
            errors.append(f"missing manifest: {manifest_path}")
            continue
        manifest = _read_json(manifest_path)
        manifest["_manifest_path"] = str(manifest_path)
        manifest["_batch_path"] = str(path)
        manifest["_summary_item"] = item
        manifests.append(manifest)
        manifest_paths.append(manifest_path)

    if len(set(manifest_paths)) != len(manifest_paths):
        errors.append("more than one recorded cell points to the same manifest")
    freeze_ids = {manifest.get("freeze", {}).get("freeze_id") for manifest in manifests}
    if freeze_ids != {batch.get("freeze_id")}:
        errors.append(f"manifest freeze ids {sorted(map(str, freeze_ids))} do not match batch")
    invalid = [manifest for manifest in manifests if manifest.get("run_validity") == "invalid"]
    if invalid:
        errors.append(f"{len(invalid)} invalid observations remain in the recorded cells")

    methods = Counter(item.get("method") for item in runs)
    splits = Counter(item.get("split") for item in runs)
    models = sorted({item.get("model") for item in runs})
    samples = sorted({int(item.get("sample_index", 0)) for item in runs})
    conditions = sorted({item.get("ablation") for item in runs if item.get("ablation")})
    if samples != [0, 1, 2]:
        errors.append(f"sample indexes are {samples}, expected [0, 1, 2]")
    if ablation:
        if methods != Counter({"m3": expected_count // 5, "m4": expected_count * 4 // 5}):
            errors.append(f"unexpected ablation method counts: {dict(methods)}")
        if conditions != sorted(ABLATIONS):
            errors.append(f"unexpected ablation conditions: {conditions}")
    else:
        expected_methods = Counter({method: 330 for method in METHODS})
        if methods != expected_methods:
            errors.append(f"unexpected primary method counts: {dict(methods)}")
        expected_splits = Counter({key: size * len(METHODS) * 3 for key, size in SPLIT_SIZES.items()})
        if splits != expected_splits:
            errors.append(f"unexpected primary split counts: {dict(splits)}")

    report = {
        "path": str(path),
        "sha256": batch.get("source_sha256", _sha256(path)),
        "status": batch.get("status"),
        "freeze_id": batch.get("freeze_id"),
        "expected_cells": expected_count,
        "recorded_cells": len(runs),
        "unique_recorded_cells": len(recorded_ids),
        "models": models,
        "methods": dict(sorted(methods.items())),
        "splits": dict(sorted(splits.items())),
        "sample_indexes": samples,
        "sample_seeds": batch.get("sample_seeds"),
        "conditions": conditions,
        "invalid_recorded_cells": len(invalid),
        "retried_infrastructure_attempts": len(batch.get("invalid_attempts", [])),
        "all_manifests_present": len(manifests) == len(runs),
        "prompt_versions": sorted(
            {str(manifest.get("prompt_version")) for manifest in manifests}
        ),
        "harness_versions": sorted(
            {str(manifest.get("harness_version")) for manifest in manifests}
        ),
        "runtime_compiler_versions": sorted(
            {str(manifest.get("runtime_compiler_version")) for manifest in manifests}
        ),
        "m5_prompt_versions": sorted(
            {
                str(manifest.get("m5_prompt_version"))
                for manifest in manifests
                if manifest.get("method", {}).get("id") == "m5"
            }
        ),
        "errors": errors,
    }
    return report, manifests


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _posthoc_key(manifest: dict[str, Any]) -> str:
    condition = (manifest.get("ablation") or {}).get("id", "primary")
    return "/".join(
        str(value)
        for value in (
            manifest.get("model", {}).get("model_id"),
            condition,
            manifest.get("method", {}).get("id"),
            manifest.get("instance", {}).get("split"),
            manifest.get("instance", {}).get("id"),
            int(manifest.get("sample_index", 0)),
        )
    )


def manifest_row(
    manifest: dict[str, Any], posthoc_main: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    method = manifest.get("method", {}).get("id")
    evaluation = manifest.get("evaluation") or {}
    summary = evaluation.get("score_summary") or evaluation.get("direct_score") or {}
    validation = evaluation.get("validation") or {}
    gates = validation.get("gate_statuses") or summary.get("gate_statuses") or {}
    usage = manifest.get("usage") or {}
    per_stage = usage.get("per_stage") or []
    reasoning_tokens = usage.get("reasoning_tokens")
    if reasoning_tokens is None:
        reasoning_tokens = sum(
            int((item.get("usage") or {}).get("reasoning_tokens") or 0) for item in per_stage
        )

    score_path = Path(manifest["_manifest_path"]).parent / "score.json"
    score = _read_json(score_path) if score_path.is_file() else {}
    binding = score.get("binding") or {}
    rates = binding.get("rates") or {}
    repair_attempts = evaluation.get("repair_attempts") or []
    initial_public_valid = None
    if method == "m4" and repair_attempts:
        initial_public_valid = float(repair_attempts[0].get("overall_status") == "pass")

    serviceflow = method in SERVICEFLOW_METHODS
    semantic_success: float | None = None
    semantic_source: str | None = None
    if serviceflow:
        if manifest.get("instance", {}).get("split") == "main":
            posthoc = posthoc_main.get(_posthoc_key(manifest))
            if posthoc is None:
                raise ValueError(f"missing post-hoc Main G6 result for {_posthoc_key(manifest)}")
            semantic_success = float(bool(posthoc.get("semantic_success")))
            semantic_source = "posthoc_scorer_1.2.1"
        else:
            semantic_success = float(summary.get("full_pass_g0_g6") is True)
            semantic_source = "frozen_manifest_nonvacuous_assertions"
    row: dict[str, Any] = {
        "model": manifest.get("model", {}).get("model_id"),
        "model_name": manifest.get("model", {}).get("model_name"),
        "method": method,
        "condition": (manifest.get("ablation") or {}).get("id", "primary"),
        "split": manifest.get("instance", {}).get("split"),
        "instance": manifest.get("instance", {}).get("id"),
        "sample_index": int(manifest.get("sample_index", 0)),
        "seed": manifest.get("model", {}).get("seed"),
        "method_status": manifest.get("method_status") or manifest.get("stopping_reason"),
        "run_validity": manifest.get("run_validity", "valid"),
        "manifest_path": _portable_path(manifest["_manifest_path"]),
        "common_gate_valid": float(all(gates.get(gate) == "pass" for gate in COMMON_GATES)),
        "executable_valid": (
            float(validation.get("overall_status") == "pass") if serviceflow else None
        ),
        "semantic_success": semantic_success,
        "semantic_scored": (1.0 if serviceflow else None),
        "semantic_source": semantic_source,
        "node_f1": float(summary.get("node_f1") or 0.0),
        "edge_f1": float(summary.get("edge_f1") or 0.0),
        "node_f1_conditional": _number(summary.get("node_f1")),
        "edge_f1_conditional": _number(summary.get("edge_f1")),
        "wiring_f1": _number(summary.get("wiring_f1")),
        "binding_top1": (
            float(summary.get("binding_top1_accuracy") or 0.0) if serviceflow else None
        ),
        "binding_version_given_correct": _number(
            binding.get("version_accuracy_given_correct_service")
        ),
        "grounded": (
            float(bool(summary.get("service_grounded"))) if method in {"m0", "m1", "m2"} else None
        ),
        "service_precision": _number(summary.get("service_precision")),
        "service_recall": _number(summary.get("service_recall")),
        "invented_service_rate": _number(rates.get("invented_service")),
        "generic_escape_hatch_rate": _number(rates.get("generic_escape_hatch")),
        "deprecated_incompatible_rate": _number(rates.get("deprecated_incompatible")),
        "first_failing_gate": summary.get("first_failing_gate")
        or validation.get("first_failing_gate"),
        "initial_executable_valid": initial_public_valid,
        "repair_conversion": (
            float(initial_public_valid == 0.0 and validation.get("overall_status") == "pass")
            if initial_public_valid is not None
            else None
        ),
        "repair_calls": sum(str(item.get("stage", "")).startswith("m4_repair") for item in per_stage),
        "llm_calls": _number(usage.get("llm_calls")),
        "prompt_tokens": _number(usage.get("prompt_tokens")),
        "completion_tokens": _number(usage.get("completion_tokens")),
        "reasoning_tokens": _number(reasoning_tokens),
        "total_tokens": _number(usage.get("total_tokens")),
        "latency_s": _number(usage.get("latency_s") or manifest.get("latency_s")),
        "cost_usd": _number(usage.get("cost_usd")),
        "validator_calls": _number(usage.get("validator_calls") or manifest.get("validator_calls")),
        "agent_steps": _number(manifest.get("agent_steps")),
        "tool_calls": _number(manifest.get("tool_calls")),
        "controller_continuations": _number(manifest.get("controller_continuations")),
        "length_truncated_calls": float(
            sum(
                str(item.get("finish_reason", "")).lower() in {"length", "max_tokens"}
                for item in per_stage
            )
        ),
    }
    for gate in GATES:
        row[f"gate_{gate}"] = float(gates.get(gate) == "pass")
    if serviceflow:
        for index, gate in enumerate(GATES):
            row[f"survival_{gate}"] = float(
                all(gates.get(required) == "pass" for required in GATES[: index + 1])
            )
    for label, count in (binding.get("confusion_by_label") or {}).items():
        row[f"confusion_{label}"] = float(count)
    return row


def _mean_present(rows: Iterable[dict[str, Any]], key: str) -> float | None:
    values = [_number(row.get(key)) for row in rows]
    present = [value for value in values if value is not None]
    return float(sum(present) / len(present)) if present else None


def aggregate_instances(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["model"], row["condition"], row["method"], row["split"], row["instance"])
        groups[key].append(row)
    metric_keys = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if isinstance(value, (int, float)) and key not in {"sample_index", "seed"}
        }
    )
    result: list[dict[str, Any]] = []
    for (model, condition, method, split, instance), items in sorted(groups.items()):
        sample_indexes = sorted(int(item["sample_index"]) for item in items)
        if sample_indexes != [0, 1, 2]:
            raise ValueError(
                f"{model}/{condition}/{method}/{split}/{instance}: samples={sample_indexes}"
            )
        entry: dict[str, Any] = {
            "model": model,
            "condition": condition,
            "method": method,
            "split": split,
            "instance": instance,
            "runs": len(items),
        }
        for key in metric_keys:
            entry[key] = _mean_present(items, key)
        result.append(entry)
    return result


def _rng_seed(label: str) -> int:
    return int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:16], 16) % (2**32)


def bca_mean(values: list[float], label: str, iterations: int = 10_000) -> tuple[float, float]:
    data = np.asarray(values, dtype=float)
    n = len(data)
    if n == 0:
        raise ValueError("BCa interval requires at least one value")
    if n == 1 or np.all(data == data[0]):
        return float(data[0]), float(data[0])
    rng = np.random.default_rng(_rng_seed(label))
    boot = data[rng.integers(0, n, size=(iterations, n))].mean(axis=1)
    observed = float(data.mean())
    proportion = (np.count_nonzero(boot < observed) + 0.5) / (iterations + 1.0)
    proportion = min(max(proportion, 1e-9), 1 - 1e-9)
    normal = NormalDist()
    z0 = normal.inv_cdf(proportion)
    jack = (data.sum() - data) / (n - 1)
    centered = jack.mean() - jack
    denominator = 6.0 * float(np.sum(centered**2) ** 1.5)
    acceleration = float(np.sum(centered**3) / denominator) if denominator else 0.0

    def adjusted(alpha: float) -> float:
        z = normal.inv_cdf(alpha)
        divisor = 1.0 - acceleration * (z0 + z)
        probability = normal.cdf(z0 + (z0 + z) / divisor) if divisor else alpha
        return min(max(probability, 0.0), 1.0)

    low, high = np.quantile(boot, [adjusted(0.025), adjusted(0.975)])
    return float(low), float(high)


def sign_flip_p(differences: list[float], label: str, iterations: int = 10_000) -> float:
    data = np.asarray(differences, dtype=float)
    if len(data) == 0 or np.allclose(data, 0.0):
        return 1.0
    observed = abs(float(data.mean()))
    rng = np.random.default_rng(_rng_seed(label))
    signs = rng.choice(np.array([-1.0, 1.0]), size=(iterations, len(data)))
    permuted = np.abs((signs * data).mean(axis=1))
    return float((np.count_nonzero(permuted >= observed - 1e-15) + 1) / (iterations + 1))


def holm_adjust(rows: list[dict[str, Any]], group_keys: tuple[str, ...]) -> None:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("p_value") is not None:
            groups[tuple(row.get(key) for key in group_keys)].append(row)
    for items in groups.values():
        ordered = sorted(items, key=lambda item: float(item["p_value"]))
        running = 0.0
        total = len(ordered)
        for index, item in enumerate(ordered):
            adjusted = min(1.0, (total - index) * float(item["p_value"]))
            running = max(running, adjusted)
            item["p_holm"] = running


def summarize(
    rows: list[dict[str, Any]], group_keys: tuple[str, ...], metrics: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in group_keys)].append(row)
    result: list[dict[str, Any]] = []
    for group, items in sorted(groups.items()):
        entry = dict(zip(group_keys, group))
        entry["instances"] = len(items)
        entry["runs"] = sum(int(item.get("runs", 0)) for item in items)
        for metric in metrics:
            values = [float(item[metric]) for item in items if item.get(metric) is not None]
            entry[f"{metric}_n"] = len(values)
            if values:
                entry[metric] = float(np.mean(values))
                low, high = bca_mean(values, f"summary/{group}/{metric}")
                entry[f"{metric}_ci_low"] = low
                entry[f"{metric}_ci_high"] = high
            else:
                entry[metric] = None
                entry[f"{metric}_ci_low"] = None
                entry[f"{metric}_ci_high"] = None
        result.append(entry)
    return result


def paired_effects(
    rows: list[dict[str, Any]],
    comparisons: tuple[tuple[str, str, str], ...],
    metrics: tuple[str, ...],
    *,
    family: str,
    condition_key: str = "method",
) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row)
    result: list[dict[str, Any]] = []
    for model, model_rows in sorted(by_model.items()):
        index = {
            (row[condition_key], row["split"], row["instance"]): row for row in model_rows
        }
        for label, left, right in comparisons:
            keys = sorted(
                {(split, instance) for cond, split, instance in index if cond == left}
                & {(split, instance) for cond, split, instance in index if cond == right}
            )
            for metric in metrics:
                paired = [
                    (index[(left, *key)].get(metric), index[(right, *key)].get(metric))
                    for key in keys
                ]
                paired = [(float(a), float(b)) for a, b in paired if a is not None and b is not None]
                if not paired:
                    continue
                differences = [right_value - left_value for left_value, right_value in paired]
                ci_low, ci_high = bca_mean(
                    differences, f"paired/{family}/{model}/{label}/{metric}"
                )
                result.append(
                    {
                        "family": family,
                        "model": model,
                        "comparison": label,
                        "left": left,
                        "right": right,
                        "metric": metric,
                        "paired_instances": len(paired),
                        "left_mean": float(np.mean([item[0] for item in paired])),
                        "right_mean": float(np.mean([item[1] for item in paired])),
                        "difference_right_minus_left": float(np.mean(differences)),
                        "ci_low": ci_low,
                        "ci_high": ci_high,
                        "p_value": sign_flip_p(
                            differences, f"perm/{family}/{model}/{label}/{metric}"
                        ),
                    }
                )
    holm_adjust(result, ("family", "model", "metric"))
    return result


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.12g}"
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    keys = sorted({key for row in rows for key in row})
    preferred = [
        key
        for key in (
            "model",
            "condition",
            "method",
            "split",
            "instance",
            "sample_index",
            "comparison",
            "metric",
        )
        if key in keys
    ]
    fieldnames = preferred + [key for key in keys if key not in preferred]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _format_percent(value: float | None) -> str:
    return "--" if value is None else f"{100 * value:.1f}"


def _report_markdown(
    validation: dict[str, Any],
    primary_summary: list[dict[str, Any]],
    ablation_summary: list[dict[str, Any]],
    ablation_effect_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Final evaluation data report",
        "",
        "Headline estimates pool all 110 pipelines. Split labels remain in the run- and "
        "instance-level exports for sensitivity analysis.",
        "",
        "## Batch validation",
        "",
        f"- Primary cells: {validation['primary']['recorded_cells']:,}/"
        f"{validation['primary']['expected_cells']:,}.",
        f"- Confirmatory ablation cells: {validation['ablation']['recorded_cells']:,}/"
        f"{validation['ablation']['expected_cells']:,}.",
        f"- Validation errors: {len(validation['errors'])}.",
        f"- Retried infrastructure attempts retained for audit: "
        f"{validation['ablation']['retried_infrastructure_attempts']}.",
        "",
        "## Primary outcomes (instance-macro means, %)",
        "",
        "| Model | Method | Public executable validity | Semantic success | Node F1 | Edge F1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in primary_summary:
        lines.append(
            f"| {MODEL_LABELS.get(row['model'], row['model'])} | {row['method']} "
            f"| {_format_percent(row.get('executable_valid'))} "
            f"| {_format_percent(row.get('semantic_success'))} "
            f"| {row['node_f1']:.3f} | {row['edge_f1']:.3f} |"
        )
    lines += [
        "",
        "Direct-Argo methods (M0--M2) have no end-to-end value because their output "
        "contract does not define G3, G4, or G6. Their applicable gate, grounding, "
        "graph, compilation, and efficiency results remain in the CSV and JSON exports.",
        "",
        "## Confirmatory ablations (Qwen3-Coder-480B, pooled 110)",
        "",
        "| Condition | Executable validity | Semantic success | Calls/run | Tokens/run |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in ablation_summary:
        lines.append(
            f"| {row['condition']} | {_format_percent(row.get('executable_valid'))} "
            f"| {_format_percent(row.get('semantic_success'))} "
            f"| {row['llm_calls']:.2f} | {row['total_tokens']:.0f} |"
        )
    lines += [
        "",
        "### Paired ablation effects",
        "",
        "Differences are condition minus the frozen v21 M4 reference.",
        "",
        "| Condition | Metric | Difference | 95% BCa CI | Holm p |",
        "|---|---|---:|---:|---:|",
    ]
    for row in ablation_effect_rows:
        if row["metric"] not in {"executable_valid", "semantic_success"}:
            continue
        scale = 100.0
        lines.append(
            f"| {row['comparison']} | {row['metric']} "
            f"| {scale * row['difference_right_minus_left']:+.1f} pp "
            f"| [{scale * row['ci_low']:+.1f}, {scale * row['ci_high']:+.1f}] "
            f"| {row.get('p_holm', row['p_value']):.4g} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--primary-batches",
        type=Path,
        nargs=3,
        default=PRIMARY_BATCHES,
        metavar=("SINTEF", "QWEN", "DEEPSEEK"),
        help="the three complete primary batch summaries",
    )
    parser.add_argument(
        "--ablation-batches",
        type=Path,
        nargs=3,
        default=ABLATION_BATCHES,
        metavar=("MAIN", "EXTENSION", "VALIDATION"),
        help="the complete Main, Extension, and Validation ablation summaries",
    )
    parser.add_argument(
        "--posthoc-main-g6",
        type=Path,
        default=POSTHOC_MAIN_G6,
        help="completed deterministic Main-40 G6 assertion audit",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.posthoc_main_g6.is_file():
        print(f"error: missing post-hoc semantic audit: {args.posthoc_main_g6}")
        return 1
    posthoc_document = _read_json(args.posthoc_main_g6)
    if posthoc_document.get("status") != "complete":
        print(f"error: post-hoc semantic audit is not complete: {args.posthoc_main_g6}")
        return 1
    posthoc_main = dict(posthoc_document.get("results") or {})

    batch_reports: list[dict[str, Any]] = []
    primary_manifests: list[dict[str, Any]] = []
    for path in args.primary_batches:
        report, manifests = validate_batch(path, ablation=False)
        batch_reports.append(report)
        primary_manifests.extend(manifests)
    ablation_manifests: list[dict[str, Any]] = []
    for path in args.ablation_batches:
        report, manifests = validate_batch(path, ablation=True)
        batch_reports.append(report)
        ablation_manifests.extend(manifests)

    all_errors = [error for report in batch_reports for error in report["errors"]]
    primary_cells = {_cell_identity(manifest["_summary_item"]) for manifest in primary_manifests}
    ablation_cells = {_cell_identity(manifest["_summary_item"]) for manifest in ablation_manifests}
    if len(primary_cells) != 5_940:
        all_errors.append(f"combined primary cells={len(primary_cells)}, expected 5940")
    if len(ablation_cells) != 1_650:
        all_errors.append(f"combined ablation cells={len(ablation_cells)}, expected 1650")

    primary_rows = [manifest_row(manifest, posthoc_main) for manifest in primary_manifests]
    ablation_rows = [manifest_row(manifest, posthoc_main) for manifest in ablation_manifests]
    primary_instances = aggregate_instances(primary_rows)
    ablation_instances = aggregate_instances(ablation_rows)

    primary_metrics = (
        "common_gate_valid",
        "executable_valid",
        "semantic_success",
        "semantic_scored",
        "node_f1",
        "edge_f1",
        "node_f1_conditional",
        "edge_f1_conditional",
        "wiring_f1",
        "binding_top1",
        "binding_version_given_correct",
        "grounded",
        "service_precision",
        "service_recall",
        "invented_service_rate",
        "generic_escape_hatch_rate",
        "deprecated_incompatible_rate",
        "llm_calls",
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_tokens",
        "latency_s",
        "cost_usd",
        "validator_calls",
        "repair_calls",
        "agent_steps",
        "tool_calls",
        "controller_continuations",
        "length_truncated_calls",
    )
    primary_summary = summarize(primary_instances, ("model", "method"), primary_metrics)
    split_summary = summarize(
        primary_instances,
        ("model", "split", "method"),
        ("executable_valid", "semantic_success", "node_f1", "edge_f1", "total_tokens"),
    )
    gate_summary = summarize(
        primary_instances,
        ("model", "method"),
        tuple(f"gate_{gate}" for gate in GATES),
    )
    gate_survival = summarize(
        [row for row in primary_instances if row["method"] in SERVICEFLOW_METHODS],
        ("model", "method"),
        tuple(f"survival_{gate}" for gate in GATES),
    )

    primary_effect_rows = paired_effects(
        primary_instances,
        (
            ("M4-M3", "m3", "m4"),
            ("M4-M5", "m5", "m4"),
        ),
        (
            "executable_valid",
            "semantic_success",
            "node_f1",
            "edge_f1",
            "binding_top1",
            "wiring_f1",
            "llm_calls",
            "total_tokens",
        ),
        family="primary",
    )

    qwen_primary = [
        row
        for row in primary_instances
        if row["model"] == "deepinfra-qwen3-coder-480b-turbo"
        and row["method"] in {"m2", "m4"}
    ]
    stage_effect_rows = paired_effects(
        qwen_primary,
        (("M2-M4 bundled stage removal", "m4", "m2"),),
        (
            "common_gate_valid",
            "gate_G0",
            "gate_G1",
            "gate_G2",
            "gate_G5",
            "node_f1",
            "edge_f1",
            "llm_calls",
            "total_tokens",
            "latency_s",
            "cost_usd",
        ),
        family="stage_sensitivity",
    )

    qwen_m4 = [
        {**row, "condition": "m4_reference"}
        for row in primary_instances
        if row["model"] == "deepinfra-qwen3-coder-480b-turbo" and row["method"] == "m4"
    ]
    ablation_with_reference = qwen_m4 + ablation_instances
    ablation_metrics = (
        "executable_valid",
        "semantic_success",
        "node_f1",
        "edge_f1",
        "binding_top1",
        "wiring_f1",
        "llm_calls",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "latency_s",
        "cost_usd",
        "repair_calls",
    )
    ablation_summary = summarize(
        ablation_with_reference, ("model", "condition"), ablation_metrics
    )
    comparisons = tuple((condition, "m4_reference", condition) for condition in ABLATIONS)
    ablation_effect_rows = paired_effects(
        ablation_with_reference,
        comparisons,
        ablation_metrics,
        family="confirmatory_ablation",
        condition_key="condition",
    )

    failure_rows: list[dict[str, Any]] = []
    for (model, method), items in sorted(
        _group(primary_rows, ("model", "method")).items()
    ):
        counts = Counter(item.get("first_failing_gate") or "none" for item in items)
        entry: dict[str, Any] = {"model": model, "method": method, "runs": len(items)}
        for category in (*GATES, "none"):
            entry[f"{category}_count"] = counts.get(category, 0)
            entry[f"{category}_rate"] = counts.get(category, 0) / len(items)
        failure_rows.append(entry)

    validation = {
        "primary": {
            "expected_cells": 5_940,
            "recorded_cells": len(primary_rows),
            "unique_cells": len(primary_cells),
            "instances": len({(row["split"], row["instance"]) for row in primary_rows}),
            "models": sorted({row["model"] for row in primary_rows}),
        },
        "ablation": {
            "expected_cells": 1_650,
            "recorded_cells": len(ablation_rows),
            "unique_cells": len(ablation_cells),
            "instances": len({(row["split"], row["instance"]) for row in ablation_rows}),
            "conditions": sorted({row["condition"] for row in ablation_rows}),
            "retried_infrastructure_attempts": sum(
                report["retried_infrastructure_attempts"] for report in batch_reports[3:]
            ),
        },
        "batches": batch_reports,
        "errors": all_errors,
        "warnings": [
            "Frozen Main-40 score files matched zero assertions because compiler scenario names differed from reviewed assertion scenario names. Semantic success uses the separate deterministic scorer-1.2.1 post-hoc audit with a guarded one-to-one alias and fail-closed mismatch handling.",
            "The SINTEF v19 M5 image/prompt predates the common DeepInfra v21/v22 M5 image/prompt; cross-provider M5 comparisons are descriptive.",
            "SINTEF provider-billed cost is unavailable; do not enter zero cost.",
            "The ablation batches used four workers while v21 used one; latency is supplementary and is not a clean paired efficiency contrast.",
            "Direct-Argo outputs do not define G3, G4, G6-Exec, or G6-Assert; end-to-end validity and semantic success are N/A for M0-M2.",
            "M0 and M1 manifests expose task.md only; the paper draft's catalog/contract-access table must be corrected.",
            "M2 uses frozen candidate/catalog inputs and does not rerun retrieval; label it catalog-grounded direct Argo, not an online retrieval result.",
            "The 24 v24 extension infrastructure attempts were excluded and successfully rerun; all 1,650 ablation cells are present.",
        ],
    }

    write_csv(args.out / "primary_run_level.csv", primary_rows)
    write_csv(args.out / "primary_instance_level.csv", primary_instances)
    write_csv(args.out / "primary_summary.csv", primary_summary)
    write_csv(args.out / "primary_split_sensitivity.csv", split_summary)
    write_csv(args.out / "primary_gate_summary.csv", gate_summary)
    write_csv(args.out / "primary_gate_survival.csv", gate_survival)
    write_csv(args.out / "primary_paired_effects.csv", primary_effect_rows)
    write_csv(args.out / "primary_failure_modes.csv", failure_rows)
    write_csv(args.out / "ablation_run_level.csv", ablation_rows)
    write_csv(args.out / "ablation_instance_level.csv", ablation_instances)
    write_csv(args.out / "ablation_summary.csv", ablation_summary)
    write_csv(args.out / "ablation_paired_effects.csv", ablation_effect_rows)
    write_csv(args.out / "stage_removal_sensitivity.csv", stage_effect_rows)
    (args.out / "batch_validation.json").write_text(
        json.dumps(validation, indent=2) + "\n", encoding="utf-8"
    )
    consolidated = {
        "validation": validation,
        "primary_summary": primary_summary,
        "primary_paired_effects": primary_effect_rows,
        "gate_summary": gate_summary,
        "gate_survival": gate_survival,
        "failure_modes": failure_rows,
        "ablation_summary": ablation_summary,
        "ablation_paired_effects": ablation_effect_rows,
        "stage_removal_sensitivity": stage_effect_rows,
    }
    (args.out / "report.json").write_text(
        json.dumps(consolidated, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "report.md").write_text(
        _report_markdown(validation, primary_summary, ablation_summary, ablation_effect_rows),
        encoding="utf-8",
    )
    if all_errors:
        print(f"validation failed with {len(all_errors)} error(s); see {args.out}")
        return 1
    print(f"validated 5,940 primary cells and 1,650 ablation cells: {args.out}")
    return 0


def _group(
    rows: list[dict[str, Any]], keys: tuple[str, ...]
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    result: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[tuple(row[key] for key in keys)].append(row)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
