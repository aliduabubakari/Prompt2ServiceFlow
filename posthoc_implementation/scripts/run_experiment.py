#!/usr/bin/env python3
"""Run experiment methods (M0-M4) over benchmark instances.

Examples:
    # smoke: M3 on one instance
    python scripts/run_experiment.py --method m3 --model local-gpt-oss-20b \
        --instances airflow_db_cleanup --allow-unfrozen

    # batch: several methods on three Main-40 instances
    python scripts/run_experiment.py --method m0,m2,m3 --model local-gpt-oss-20b \
        --split main --limit 3 --allow-unfrozen

    # M4 with a custom repair budget
    python scripts/run_experiment.py --method m4 --model local-gpt-oss-20b \
        --instances airflow_db_cleanup --repair-budget 3 --allow-unfrozen
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from prompt2serviceflow.experiments.harness import run_batch  # noqa: E402
from prompt2serviceflow.experiments.llm import load_model_configs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--method", required=True, help="comma-separated method ids (m0..m4)")
    parser.add_argument("--model", required=True, help="model id from the roster config")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "config" / "models.json",
        help="model roster JSON",
    )
    parser.add_argument("--split", default="main", choices=["main", "validation", "all"])
    parser.add_argument("--instances", nargs="*", default=None, help="explicit instance ids")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of instances")
    parser.add_argument("--repair-budget", type=int, default=3, help="M4 repair budget (default 3)")
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="independent samples per method/instance (use 3 or 5 for pass@k)",
    )
    parser.add_argument("--no-exec", action="store_true", help="skip execution-based gates/scoring")
    parser.add_argument(
        "--repair-no-exec",
        action="store_true",
        help="A9: withhold G6-Exec during M4 repair but still execute final evaluation",
    )
    parser.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="development/smoke only: allow a candidate or drifted freeze",
    )
    parser.add_argument(
        "--allow-validation-rerun",
        action="store_true",
        help="override the one-shot Validation-20 lock after documenting invalidation",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "runs",
        help="where run directories are written",
    )
    parser.add_argument(
        "--workspaces-root",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "workspaces",
    )
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=PROJECT_ROOT / "benchmark",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    roster = load_model_configs(args.config)
    if args.model not in roster:
        print(
            f"error: model {args.model!r} not in roster; available: {sorted(roster)}",
            file=sys.stderr,
        )
        return 2
    method_ids = [item.strip() for item in args.method.split(",") if item.strip()]
    unknown = [item for item in method_ids if item not in {"m0", "m1", "m2", "m3", "m4"}]
    if unknown:
        print(f"error: unknown method ids: {unknown}", file=sys.stderr)
        return 2
    splits = ("main", "validation") if args.split == "all" else (args.split,)
    try:
        summary = run_batch(
            method_ids,
            workspaces_root=args.workspaces_root,
            benchmark_root=args.benchmark_root,
            model=roster[args.model],
            splits=splits,
            instance_ids=args.instances,
            limit=args.limit,
            runs_root=args.runs_root,
            repair_budget=args.repair_budget,
            run_execution=not args.no_exec,
            repair_with_execution=False if args.repair_no_exec else None,
            samples_per_instance=args.samples,
            allow_unfrozen=args.allow_unfrozen,
            allow_validation_rerun=args.allow_validation_rerun,
            roster_path=args.config,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"completed {summary['run_count']} runs")
    for run in summary["runs"]:
        evaluation = run["evaluation"]
        if "score_summary" in evaluation:
            status = evaluation["score_summary"].get("full_pass_g0_g6")
        elif "direct_score" in evaluation:
            status = f"grounded={evaluation['direct_score'].get('service_grounded')}"
        else:
            status = run["method_status"]
        print(
            f"  {run['method']} {run['instance']}: {run['method_status']} "
            f"-> {status} ({run['usage']['total_tokens']} tokens)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
