#!/usr/bin/env python3
"""Run the M5 agentic method on one instance inside an isolated container.

Example:
    python scripts/run_m5_agent.py --instance airflow_db_cleanup \
        --model local-gpt-oss-20b --repair-budget 3 --allow-unfrozen

The agent container sees only its staged workspace; the model API key stays
in the proxy container. Requires Docker.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from prompt2serviceflow.experiments.agentic import (  # noqa: E402
    DEFAULT_M5_AGENT_STEPS,
    DEFAULT_M5_TIMEOUT_SECONDS,
    DEFAULT_M5_TOKEN_CAP,
    run_m5,
)
from prompt2serviceflow.experiments.llm import load_model_configs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--instance", required=True, help="instance id")
    parser.add_argument("--split", default="main", choices=["main", "validation"])
    parser.add_argument("--model", required=True, help="model id from the roster config")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "config" / "models.json",
    )
    parser.add_argument(
        "--repair-budget",
        type=int,
        default=3,
        help="M4 repair budget B; M5's validator-call budget is derived as B+1",
    )
    parser.add_argument("--token-cap", type=int, default=DEFAULT_M5_TOKEN_CAP)
    parser.add_argument("--timeout-s", type=int, default=DEFAULT_M5_TIMEOUT_SECONDS)
    parser.add_argument("--agent-steps", type=int, default=DEFAULT_M5_AGENT_STEPS)
    parser.add_argument(
        "--freeze-config",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "config" / "freeze.json",
    )
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "experiments" / "runs")
    parser.add_argument(
        "--workspaces-root", type=Path, default=PROJECT_ROOT / "experiments" / "workspaces"
    )
    parser.add_argument("--benchmark-root", type=Path, default=PROJECT_ROOT / "benchmark")
    parser.add_argument(
        "--skip-image-build", action="store_true", help="reuse existing p2sf-m5 images"
    )
    parser.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="development/smoke only: allow a candidate or drifted freeze",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    roster = load_model_configs(args.config)
    if args.model not in roster:
        print(f"error: model {args.model!r} not in roster {sorted(roster)}", file=sys.stderr)
        return 2
    workspace = args.workspaces_root / args.split / args.instance
    instance_dir = args.benchmark_root / "instances" / args.split / args.instance
    if not workspace.is_dir() or not instance_dir.is_dir():
        print(
            f"error: workspace or instance not found for {args.split}/{args.instance}",
            file=sys.stderr,
        )
        return 2
    from prompt2serviceflow.experiments.freeze import check_freeze
    from prompt2serviceflow.experiments.leakage import scan_workspace

    freeze, freeze_errors = check_freeze(
        freeze_path=args.freeze_config,
        roster_path=args.config,
        repair_budget=args.repair_budget,
        model_id=args.model,
        require_frozen=not args.allow_unfrozen,
        include_m5=True,
    )
    if freeze_errors and not args.allow_unfrozen:
        print(f"error: freeze mismatch: {'; '.join(freeze_errors)}", file=sys.stderr)
        return 1
    findings = scan_workspace(workspace)
    if findings:
        print(
            f"error: workspace leakage/integrity gate found {len(findings)} issues", file=sys.stderr
        )
        return 1
    from datetime import datetime, timezone

    run_id = (
        f"m5__{args.split}__{args.instance}__{args.model}__"
        f"s0__{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__"
        f"{uuid.uuid4().hex[:8]}"
    )
    from prompt2serviceflow.experiments.methods import validator_budget_for

    validator_budget = validator_budget_for(args.repair_budget)
    print(f"validator budget: {validator_budget} (derived from repair budget {args.repair_budget})")
    manifest = run_m5(
        workspace=workspace,
        instance_dir=instance_dir,
        model=roster[args.model],
        run_dir=args.runs_root / run_id,
        validator_budget=validator_budget,
        token_cap=args.token_cap,
        timeout_s=args.timeout_s,
        agent_step_budget=args.agent_steps,
        roster_path=args.config,
        skip_image_build=args.skip_image_build,
        freeze_document=freeze,
        freeze_errors_ignored=freeze_errors if args.allow_unfrozen else [],
    )
    print(
        f"run: {manifest.get('stopping_reason')} | validator calls: "
        f"{manifest.get('validator_calls')} | tool calls: {manifest.get('tool_calls')}"
    )
    evaluation = manifest.get("evaluation", {})
    if "score_summary" in evaluation:
        print(f"score: {evaluation['score_summary']}")
    else:
        print(f"evaluation: {evaluation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
