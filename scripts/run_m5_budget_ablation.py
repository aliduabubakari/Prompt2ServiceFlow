#!/usr/bin/env python3
"""Run or resume the frozen A13 M5 validator-budget sensitivity study."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from prompt2serviceflow.experiments.agentic import run_m5  # noqa: E402
from prompt2serviceflow.experiments.freeze import check_freeze  # noqa: E402
from prompt2serviceflow.experiments.leakage import scan_workspace_root  # noqa: E402
from prompt2serviceflow.experiments.llm import (  # noqa: E402
    OpenAICompatibleClient,
    UsageLedger,
    load_model_configs,
)


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "experiments/config/models.json"
    )
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "experiments/runs")
    parser.add_argument(
        "--workspaces-root", type=Path, default=PROJECT_ROOT / "experiments/workspaces"
    )
    parser.add_argument("--benchmark-root", type=Path, default=PROJECT_ROOT / "benchmark")
    parser.add_argument("--batch-summary", type=Path, default=None)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--allow-unfrozen", action="store_true")
    parser.add_argument("--skip-image-build", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    load_dotenv(PROJECT_ROOT / ".env")
    roster = load_model_configs(args.config)
    freeze, errors = check_freeze(
        roster_path=args.config,
        require_frozen=not args.allow_unfrozen,
        include_m5=True,
    )
    if errors and not args.allow_unfrozen:
        print(f"error: freeze mismatch: {'; '.join(errors)}", file=sys.stderr)
        return 1
    if args.samples < 1:
        print("error: samples must be positive", file=sys.stderr)
        return 2
    leakage = scan_workspace_root(args.workspaces_root)
    if leakage["status"] != "pass":
        print(f"error: leakage gate found {leakage['finding_count']} issues", file=sys.stderr)
        return 1

    protocol = freeze["a13"]
    model_id = protocol["model"]
    model = roster[model_id]
    budgets = list(protocol["validator_budgets"])
    instances = list(protocol["main_subset"])
    for instance_id in instances:
        if not (args.workspaces_root / "main" / instance_id).is_dir():
            print(f"error: frozen A13 workspace is missing: {instance_id}", file=sys.stderr)
            return 1

    probe = OpenAICompatibleClient(model, UsageLedger(), max_retries=1).complete(
        stage="a13_preflight", system="Reply exactly with OK.", user="OK"
    )
    if probe.text.strip() != "OK":
        print(f"error: model preflight returned {probe.text.strip()!r}", file=sys.stderr)
        return 1

    design = {
        "freeze_id": freeze["freeze_id"],
        "model": model_id,
        "split": "main",
        "instances": instances,
        "validator_budgets": budgets,
        "samples_per_instance": args.samples,
    }
    if args.batch_summary:
        summary_path = args.batch_summary.resolve()
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot resume A13 summary: {exc}", file=sys.stderr)
            return 2
        mismatches = [
            f"{key}: batch={summary.get(key)!r}, requested={value!r}"
            for key, value in design.items()
            if summary.get(key) != value
        ]
        if mismatches:
            print(f"error: immutable A13 design mismatch: {'; '.join(mismatches)}", file=sys.stderr)
            return 2
        batch_id = summary["batch_id"]
    else:
        batch_id = (
            f"a13__{model_id}__"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__"
            f"{uuid.uuid4().hex[:8]}"
        )
        summary_path = args.runs_root / f"{batch_id}.json"
        summary = {
            **design,
            "status": "running",
            "batch_id": batch_id,
            "resolved_model": probe.model,
            "expected_cells": [
                {
                    "model": model_id,
                    "method": "m5",
                    "split": "main",
                    "instance": instance_id,
                    "sample_index": sample_index,
                    "validator_budget": budget,
                    "ablation": f"a13_validator_budget_{budget}",
                }
                for instance_id in instances
                for sample_index in range(args.samples)
                for budget in budgets
            ],
            "runs": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(summary_path, summary)

    completed = {
        (item["instance"], item["sample_index"], item["validator_budget"])
        for item in summary.get("runs", [])
        if item.get("status") == "recorded"
    }
    image_ready = args.skip_image_build or bool(completed)
    for instance_id in instances:
        workspace = args.workspaces_root / "main" / instance_id
        instance = args.benchmark_root / "instances" / "main" / instance_id
        for sample_index in range(args.samples):
            for budget in budgets:
                cell = (instance_id, sample_index, budget)
                if cell in completed:
                    continue
                condition = f"a13_validator_budget_{budget}"
                run_id = (
                    f"m5__main__{instance_id}__{model_id}__{condition}__s{sample_index}__"
                    f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__"
                    f"{uuid.uuid4().hex[:8]}"
                )
                run_dir = args.runs_root / run_id
                manifest = run_m5(
                    workspace=workspace,
                    instance_dir=instance,
                    model=model,
                    run_dir=run_dir,
                    validator_budget=budget,
                    skip_image_build=image_ready,
                    freeze_document=freeze,
                    freeze_errors_ignored=errors if args.allow_unfrozen else [],
                    batch_id=batch_id,
                    sample_index=sample_index,
                    ablation={"id": condition, "validator_budget": budget},
                )
                image_ready = True
                summary["runs"].append(
                    {
                        "status": "recorded",
                        "model": model_id,
                        "method": "m5",
                        "split": "main",
                        "instance": instance_id,
                        "sample_index": sample_index,
                        "validator_budget": budget,
                        "ablation": condition,
                        "run_id": manifest["run_id"],
                        "manifest_path": str((run_dir / "manifest.json").resolve()),
                    }
                )
                completed.add(cell)
                _write_json(summary_path, summary)
                print(f"recorded {condition} {instance_id} sample={sample_index}")

    expected = len(instances) * len(budgets) * args.samples
    if len(completed) != expected:
        print(f"error: A13 batch has {len(completed)}/{expected} cells", file=sys.stderr)
        return 1
    summary.update(
        {
            "status": "complete",
            "expected_cell_count": expected,
            "recorded_cell_count": len(completed),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_json(summary_path, summary)
    print(f"complete: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
