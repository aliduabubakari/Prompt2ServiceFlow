#!/usr/bin/env python3
"""Offline reproduction entry point; never calls models or executes submissions.

The all-results mode fails closed while declared submission-release blockers
remain. The original and accounting modes qualify only their named scope.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--posthoc-root", type=Path, help="Extracted content-addressed profile-38.1 evidence")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--mode", choices=("all", "original", "accounting", "posthoc"), default="all")
    args = parser.parse_args()
    root = args.repository_root.resolve()
    evidence = (args.evidence_root or root).resolve()
    out = (args.out or root / "results/regenerated/submission").resolve()
    out.mkdir(parents=True, exist_ok=True)
    status = {"scope": args.mode, "model_calls": 0, "generated_code_execution": False,
              "checks": {}, "release_ready": False}

    def run(script, *options):
        subprocess.run([sys.executable, "-B", str(root / "scripts" / script), *map(str, options)], cwd=root, check=True)

    try:
        if args.mode in {"all", "original"}:
            primary = ["results/paper/batch_summaries/" + name for name in (
                "primary-sintef-v19.json", "primary-qwen480-v21.json", "primary-deepseek41-v22.json")]
            ablation = ["results/paper/batch_summaries/" + name for name in (
                "ablation-main-v24.json", "ablation-extension-v24.json", "ablation-validation-v24.json")]
            run("prepare_evaluation_final_results.py", "--primary-batches", *primary,
                "--ablation-batches", *ablation, "--posthoc-main-g6",
                "results/paper/analysis/posthoc_main_g6_assert.json", "--out", out / "original")
            run("verify_analysis_bundle.py", "--expected", root / "results/paper/analysis", "--actual", out / "original")
            status["checks"]["original_analysis"] = "pass"
        if args.mode in {"all", "accounting"}:
            run("audit_m5_accounting.py", "--evidence-root", evidence, "--out", out / "accounting")
            with (out / "accounting/summary.csv").open(newline="") as handle:
                summaries = list(csv.DictReader(handle))
            index = {(row["model"], row["method"]): row for row in summaries}
            expected = json.loads((root / "replication/expected_results.json").read_text())
            table = []
            for model in ("DeepSeek-Flash", "Qwen-480B", "Qwen-27B"):
                for method in ("m3", "m4", "m5"):
                    row = index[model, method]
                    bound = model == "Qwen-27B" and method == "m5"
                    calls = float(row["successful_completions_lower_bound_mean"] if bound else row["successful_completions_mean"])
                    cost = float(row["standardized_cost_usd_mean"]) if row["standardized_cost_usd_mean"] else None
                    tokens = float(row["recorded_total_tokens_mean"])
                    table.append({"model": model, "method": method.upper(), "successful_completions": f"{calls:.2f}",
                                  "completion_count_is_lower_bound": bound, "tokens": round(tokens),
                                  "standardized_cost_usd": f"{cost:.4f}" if cost is not None else ""})
                    if method == "m5":
                        target = expected["table10_m5"][model]
                        desired = target.get("successful_completions", target.get("successful_completions_display"))
                        if round(calls, 2) != desired or round(tokens) != target["tokens"]:
                            raise ValueError(f"Table 10 mismatch: {model}")
                        if cost is not None and round(cost, 4) != target["standardized_cost_usd"]:
                            raise ValueError(f"Standardized cost mismatch: {model}")
            with (out / "table10.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(table[0]))
                writer.writeheader()
                writer.writerows(table)
            tex = [r"\begin{tabular}{llrrr}", r"Model & Method & Successful completions & Tokens & Standardized USD \\"]
            for row in table:
                # A star preserves the PDF's displayed value and caption qualification.
                calls = row["successful_completions"] + (r"$^{*}$" if row["completion_count_is_lower_bound"] else "")
                tex.append(f"{row['model']} & {row['method']} & {calls} & {row['tokens']:,} & {row['standardized_cost_usd'] or '--'} " + r"\\")
            tex.extend([r"\end{tabular}", "% * Qwen-27B M5 is a lower bound from incomplete proxy evidence plus transcript witnesses."])
            (out / "table10.tex").write_text("\n".join(tex) + "\n")
            status["checks"]["table10_m5_pdf_targets"] = "pass"
        if args.mode in {"all", "posthoc"}:
            if args.posthoc_root is None:
                raise ValueError("Supply --posthoc-root with the extracted profile-38.1 evidence directory")
            run("reproduce_posthoc_results.py", "--evidence-root", args.posthoc_root.resolve(), "--out", out / "posthoc")
            status["checks"]["posthoc_seals_roster_and_table6"] = "pass"
        blockers = json.loads((root / "replication/RELEASE_MANIFEST.json").read_text())["release_blockers"]
        status["release_blockers"] = blockers
        status["release_ready"] = not blockers and args.mode == "all"
        status["release_scope"] = "Framework results; corpus Table 4 is maintained externally"
        status["status"] = "blocked" if args.mode == "all" and blockers else "pass_for_selected_scope"
        code = 2 if status["status"] == "blocked" else 0
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as exc:
        status["status"] = "failed"
        status["error"] = str(exc)
        code = 1
    (out / "verification.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
