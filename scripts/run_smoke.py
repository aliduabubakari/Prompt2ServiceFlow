#!/usr/bin/env python3
"""Primary smoke run: M0-M4 over a stratified Main-40 subset.

Default subset (topology x complexity, derived from gold control flow):

    daily_sales_report             linear          simple    (4 intents)
    customer_dq_scoring_pipeline   fan-out/fan-in  moderate  (6 intents)
    fraud_detection_triage         branch/merge    moderate  (5 intents)
    hive_script                    linear          simple    (2 intents)
    airflow_db_cleanup             fan-out/fan-in  complex   (14 intents)

Pre-flight checks run before any LLM call: workspaces present, leakage gate
clean, and a minimal auth probe against the configured provider. M5 is
exploratory and runs only when explicitly requested with ``--include-m5``.
Writes a consolidated smoke report under experiments/runs/smoke_<ts>/.

Usage:
    python scripts/run_smoke.py --model local-gpt-oss-20b --allow-unfrozen
    python scripts/run_smoke.py --model local-gpt-oss-20b --include-m5 --allow-unfrozen
    python scripts/run_smoke.py --model local-gpt-oss-20b \
        --instances daily_sales_report --allow-unfrozen
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

from prompt2serviceflow.experiments.agentic import (  # noqa: E402
    AGENT_IMAGE_TAG,
    DEFAULT_M5_TIMEOUT_SECONDS,
    DEFAULT_M5_TOKEN_CAP,
    M5_VERSION,
    PROXY_IMAGE_TAG,
    run_m5,
)
from prompt2serviceflow.experiments.harness import run_batch  # noqa: E402
from prompt2serviceflow.experiments.leakage import scan_workspace_root  # noqa: E402
from prompt2serviceflow.experiments.llm import (  # noqa: E402
    OpenAICompatibleClient,
    UsageLedger,
    load_model_configs,
)

DEFAULT_SUBSET = [
    "hive_script",
    "daily_sales_report",
    "customer_dq_scoring_pipeline",
    "fraud_detection_triage",
    "airflow_db_cleanup",
]


def _auth_probe(model) -> tuple[bool, str]:
    """Minimal exact completion to verify a keyless or authenticated provider."""
    try:
        result = OpenAICompatibleClient(model, UsageLedger(), max_retries=1).complete(
            stage="smoke_preflight", system="Reply exactly with OK.", user="OK"
        )
        ok = result.text.strip() == "OK"
        return ok, f"endpoint {'ok' if ok else 'unexpected response'} ({result.text.strip()!r})"
    except Exception as exc:
        return False, f"auth probe failed: {exc}"


def _preflight(args, model, subset) -> list[str]:
    problems: list[str] = []
    for instance in subset:
        if not (args.workspaces_root / "main" / instance / "workspace.yaml").is_file():
            problems.append(f"workspace missing: main/{instance}")
    if problems:
        return problems
    report = scan_workspace_root(args.workspaces_root)
    if report["status"] != "pass":
        problems.append(f"leakage gate FAIL: {report['finding_count']} findings")
    if args.include_m5 and not args.skip_m5:
        import shutil
        import subprocess

        if shutil.which("docker") is None:
            problems.append("docker not available (needed for --include-m5)")
        else:
            for tag in (f"{AGENT_IMAGE_TAG}:{M5_VERSION}", f"{PROXY_IMAGE_TAG}:{M5_VERSION}"):
                completed = subprocess.run(["docker", "image", "inspect", tag], capture_output=True)
                if completed.returncode and args.skip_image_build:
                    problems.append(f"M5 image missing: {tag} (build via run_m5_agent.py)")
    ok, message = _auth_probe(model)
    print(f"  auth probe: {message}")
    if not ok:
        problems.append(message)
    return problems


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "experiments" / "config" / "models.json"
    )
    parser.add_argument("--instances", nargs="*", default=None)
    parser.add_argument(
        "--repair-budget",
        type=int,
        default=3,
        help="M4 repair budget; exploratory M5 derives its validator budget as B+1",
    )
    parser.add_argument("--m5-timeout-s", type=int, default=DEFAULT_M5_TIMEOUT_SECONDS)
    parser.add_argument("--m5-token-cap", type=int, default=DEFAULT_M5_TOKEN_CAP)
    parser.add_argument(
        "--include-m5",
        action="store_true",
        help="also run the exploratory M5 controller",
    )
    parser.add_argument("--skip-m5", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-image-build", action="store_true")
    parser.add_argument("--allow-unfrozen", action="store_true")
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "experiments" / "runs")
    parser.add_argument(
        "--workspaces-root", type=Path, default=PROJECT_ROOT / "experiments" / "workspaces"
    )
    parser.add_argument("--benchmark-root", type=Path, default=PROJECT_ROOT / "benchmark")
    return parser.parse_args()


def _row_from_batch(run: dict) -> dict:
    evaluation = run["evaluation"]
    row = {
        "method": run["method"],
        "instance": run["instance"],
        "status": run["method_status"],
        "tokens": run["usage"]["total_tokens"],
        "latency_s": run["usage"]["latency_s"],
        "cost_usd": run["usage"]["cost_usd"],
    }
    if "score_summary" in evaluation:
        summary = evaluation["score_summary"]
        row.update(
            {
                "full_pass": summary.get("full_pass_g0_g6"),
                "first_failing_gate": summary.get("first_failing_gate"),
                "node_f1": summary.get("node_f1"),
                "edge_f1": summary.get("edge_f1"),
                "binding_top1": summary.get("binding_top1_accuracy"),
            }
        )
    elif "direct_score" in evaluation:
        score = evaluation["direct_score"]
        row.update(
            {
                "full_pass": None,
                "grounded": score.get("service_grounded"),
                "service_precision": score.get("service_precision"),
                "service_recall": score.get("service_recall"),
            }
        )
    return row


def main() -> int:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    roster = load_model_configs(args.config)
    if args.model not in roster:
        print(f"error: model {args.model!r} not in roster {sorted(roster)}", file=sys.stderr)
        return 2
    model = roster[args.model]
    subset = args.instances or DEFAULT_SUBSET
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    smoke_dir = args.runs_root / f"smoke_{stamp}"
    smoke_dir.mkdir(parents=True, exist_ok=True)

    print(f"smoke subset: {subset}")
    print("pre-flight checks...")
    problems = _preflight(args, model, subset)
    if problems:
        for problem in problems:
            print(f"  ERROR: {problem}")
        return 1
    print("pre-flight OK\n")

    started = time.time()
    methods = ["m0", "m1", "m2", "m3", "m4"]
    print(f"=== phase A: {methods} on {len(subset)} instances ===")
    batch = run_batch(
        methods,
        workspaces_root=args.workspaces_root,
        benchmark_root=args.benchmark_root,
        model=model,
        splits=("main",),
        instance_ids=subset,
        runs_root=smoke_dir / "m0_m4",
        repair_budget=args.repair_budget,
        allow_unfrozen=args.allow_unfrozen,
        roster_path=args.config,
    )
    rows = [_row_from_batch(run) for run in batch["runs"]]

    if args.include_m5 and not args.skip_m5:
        print("\n=== phase B: m5 on each instance ===")
        from prompt2serviceflow.experiments.freeze import check_freeze

        freeze, freeze_errors = check_freeze(
            roster_path=args.config,
            repair_budget=args.repair_budget,
            model_id=args.model,
            require_frozen=not args.allow_unfrozen,
            include_m5=True,
        )
        image_ready = args.skip_image_build
        for instance in subset:
            print(f"  m5 {instance} ...", flush=True)
            run_id = (
                f"m5__main__{instance}__{args.model}__"
                f"s0__{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}__"
                f"{uuid.uuid4().hex[:8]}"
            )
            from prompt2serviceflow.experiments.methods import validator_budget_for

            m5_budget = validator_budget_for(args.repair_budget)
            manifest = run_m5(
                workspace=args.workspaces_root / "main" / instance,
                instance_dir=args.benchmark_root / "instances" / "main" / instance,
                model=model,
                run_dir=smoke_dir / "m5" / run_id,
                validator_budget=m5_budget,
                token_cap=args.m5_token_cap,
                timeout_s=args.m5_timeout_s,
                skip_image_build=image_ready,
                freeze_document=freeze,
                freeze_errors_ignored=freeze_errors if args.allow_unfrozen else [],
            )
            image_ready = True
            row = {
                "method": "m5",
                "instance": instance,
                "status": manifest["stopping_reason"],
                "validator_calls": manifest.get("validator_calls"),
                "tool_calls": manifest.get("tool_calls"),
            }
            summary = manifest.get("evaluation", {}).get("score_summary")
            if summary:
                row.update(
                    {
                        "full_pass": summary.get("full_pass_g0_g6"),
                        "first_failing_gate": summary.get("first_failing_gate"),
                        "node_f1": summary.get("node_f1"),
                        "binding_top1": summary.get("binding_top1_accuracy"),
                    }
                )
            rows.append(row)
            print(
                f"    -> {row['status']} | full_pass={row.get('full_pass')} | "
                f"validator_calls={row.get('validator_calls')} | tool_calls={row.get('tool_calls')}"
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {"model_id": model.model_id, "model_name": model.model_name},
        "subset": subset,
        "repair_budget": args.repair_budget,
        "elapsed_s": round(time.time() - started, 1),
        "rows": rows,
    }
    (smoke_dir / "smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")

    def fmt(value) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    lines = [
        f"# Smoke report {stamp} (model: {model.model_id})",
        "",
        "| instance | method | status | full_pass | first_fail | node_f1 | edge_f1 | bind@1 | tokens |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['instance']} | {row['method']} | {row['status']} "
            f"| {fmt(row.get('full_pass'))} | {fmt(row.get('first_failing_gate'))} "
            f"| {fmt(row.get('node_f1'))} | {fmt(row.get('edge_f1'))} "
            f"| {fmt(row.get('binding_top1'))} | {fmt(row.get('tokens'))} |"
        )
    (smoke_dir / "smoke_report.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[2:]))
    print(f"\nreport: {smoke_dir}/smoke_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
