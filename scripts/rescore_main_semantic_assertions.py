#!/usr/bin/env python3
"""Re-score assertion-bearing Main-40 outputs after the scenario-name fix.

Generation manifests remain immutable. Only public-validator-passing cells can
achieve semantic success, so the script re-executes those cells and records a
separate post-hoc evaluation artifact for the final analysis bundle.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt2serviceflow.experiments.scoring import (  # noqa: E402
    REPORT_VERSION,
    TOOL_NAME,
    TOOL_VERSION,
    _score_g6_assert,
)


PRIMARY_BATCHES = (
    ROOT
    / "experiments/runs/frozen__freeze-2026-10-01.sintef.v19__20261001T204646.947784Z__7da3753f.json",
    ROOT
    / "experiments/runs/qwen480-v21/frozen__freeze-2026-10-08.deepinfra.v21__20261008T100403.597052Z__486e18ae.json",
    ROOT
    / "experiments/runs/deepseek41-v22/frozen__freeze-2026-10-08.deepinfra.v22__20261008T100403.076491Z__f390947e.json",
)
ABLATION_MAIN_BATCH = (
    ROOT
    / "experiments/runs/ablation-qwen-v24/ablations__deepinfra-qwen3-coder-480b-turbo__20261010T195909.668288Z__69c9456f.json"
)
OUTPUT = ROOT / "experiments/analysis/evaluation_final/posthoc_main_g6_assert.json"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(item: dict[str, Any]) -> str:
    condition = item.get("ablation") or "primary"
    return "/".join(
        str(value)
        for value in (
            item["model"],
            condition,
            item["method"],
            item["split"],
            item["instance"],
            item["sample_index"],
        )
    )


def _submission_dir(manifest_path: Path, method: str) -> Path:
    run_dir = manifest_path.parent
    score_path = run_dir / "score.json"
    if score_path.is_file():
        submission = (_read(score_path).get("submission") or "").strip()
        if submission:
            path = Path(submission)
            return path if path.is_absolute() else ROOT / path
    if method in {"m3", "m4"}:
        return run_dir / "submission"
    return run_dir / "agent_workspace" / "submission"


def _score(task: tuple[dict[str, Any], Path, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    item, manifest_path, manifest = task
    key = _cell(item)
    validation = (manifest.get("evaluation") or {}).get("validation") or {}
    if validation.get("overall_status") != "pass":
        return key, {
            "status": "not_executed_public_invalid",
            "semantic_success": False,
            "original_public_status": validation.get("overall_status", "missing"),
        }
    workspace_manifest = Path(manifest["visible_input_policy"]["workspace_manifest"])
    instance_dir = (
        Path(manifest.get("_benchmark_root", ROOT / "benchmark"))
        / "instances"
        / item["split"]
        / item["instance"]
    )
    report = _score_g6_assert(
        instance_dir,
        workspace_manifest.parent,
        _submission_dir(manifest_path, item["method"]),
    )
    return key, {
        "status": "rescored",
        "semantic_success": report.get("overall_status") == "pass",
        "g6_assert": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--primary-batches",
        type=Path,
        nargs=3,
        default=PRIMARY_BATCHES,
        metavar=("SINTEF", "QWEN", "DEEPSEEK"),
    )
    parser.add_argument(
        "--ablation-main-batch", type=Path, default=ABLATION_MAIN_BATCH
    )
    parser.add_argument("--benchmark-root", type=Path, default=ROOT / "benchmark")
    args = parser.parse_args()
    tasks: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
    for batch_path in (*args.primary_batches, args.ablation_main_batch):
        batch = _read(batch_path)
        for item in batch.get("runs", []):
            if item.get("split") != "main" or item.get("method") not in {"m3", "m4", "m5"}:
                continue
            manifest_path = Path(item["manifest_path"])
            if not manifest_path.is_absolute():
                repository_path = ROOT / manifest_path
                manifest_path = (repository_path if repository_path.is_file()
                                 else batch_path.parent / manifest_path).resolve()
            manifest = _read(manifest_path)
            workspace_manifest = Path(manifest["visible_input_policy"]["workspace_manifest"])
            if not workspace_manifest.is_absolute():
                manifest["visible_input_policy"]["workspace_manifest"] = str(
                    (ROOT / workspace_manifest).resolve()
                )
            manifest["_benchmark_root"] = str(args.benchmark_root.resolve())
            tasks.append((item, manifest_path, manifest))
    if len(tasks) != 1_680:
        print(f"error: selected {len(tasks)} Main serviceflow cells, expected 1680", file=sys.stderr)
        return 1

    selected_count = len(tasks)
    if args.output.is_file():
        previous = _read(args.output)
        previous_results = dict(previous.get("results") or {})
        # Version 1 keys omitted the ablation condition and cannot represent
        # the four M4 ablation cells sharing a method/instance/seed identity.
        results = (
            previous_results
            if all(len(key.split("/")) == 6 for key in previous_results)
            else {}
        )
    else:
        results: dict[str, dict[str, Any]] = {}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(status: str) -> None:
        document = {
            "status": status,
            "purpose": "post-hoc deterministic G6-Assert re-score after one-to-one scenario alias fix",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
            "report_version": REPORT_VERSION,
            "selected_cells": selected_count,
            "recorded_cells": len(results),
            "locally_reexecuted_cells": sum(
                item["status"] == "rescored" for item in results.values()
            ),
            "public_invalid_cells": sum(
                item["status"] == "not_executed_public_invalid" for item in results.values()
            ),
            "semantic_successes": sum(
                bool(item["semantic_success"]) for item in results.values()
            ),
            "results": dict(sorted(results.items())),
        }
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.output)

    tasks = [task for task in tasks if _cell(task[0]) not in results]
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(_score, task): task for task in tasks}
        for index, future in enumerate(as_completed(futures), 1):
            try:
                key, result = future.result()
            except Exception as exc:
                item, _, _ = futures[future]
                key = _cell(item)
                result = {
                    "status": "rescore_error",
                    "semantic_success": False,
                    "error": str(exc),
                }
            results[key] = result
            if index % 25 == 0 or index == len(tasks):
                checkpoint("running")
                print(f"scored {len(results)}/{selected_count} cells")
    checkpoint("complete")
    print(f"complete: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
