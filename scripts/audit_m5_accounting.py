#!/usr/bin/env python3
"""Audit saved M5 accounting and step-12 artifact changes without running models.

Only the requested output directory is written. Frozen manifests, proxy logs,
transcripts, published analysis, and the manuscript are never modified.
The step sensitivity is a trace inspection, not a strict-budget replay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "experiments/analysis/evaluation_final"
LABELS = {
    "sintef-qwen3-8-27b-nvfp4": "Qwen-27B",
    "deepinfra-qwen3-coder-480b-turbo": "Qwen-480B",
    "deepinfra-deepseek-v4-1-flash": "DeepSeek-Flash",
}
CONFIGS = {
    "Qwen-480B": "experiments/config/models.deepinfra.v21.json",
    "DeepSeek-Flash": "experiments/config/models.deepinfra.v22.json",
}
CLEANUP = 'cd /workspace && rm -f gen_ir.py diagnostics.json && ls submission && echo "---" && ls submission/runtime submission/argo'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "experiments/analysis/m5_accounting_audit_v1")
    parser.add_argument("--evidence-root", type=Path, default=ROOT,
                        help="Repository or archive root containing results/paper or the original experiment records")
    args = parser.parse_args()
    evidence = args.evidence_root.resolve()
    hashes: dict[str, str] = {}

    def source(path: Path) -> str:
        data = path.read_bytes()
        try:
            name = path.relative_to(ROOT).as_posix()
        except ValueError:
            name = "evidence/" + path.relative_to(evidence).as_posix()
        hashes[name] = hashlib.sha256(data).hexdigest()
        return data.decode("utf-8")

    def read_json(path: Path) -> dict:
        return json.loads(source(path))

    def jsonl(path: Path) -> tuple[list[dict], list[int]]:
        events, malformed = [], []
        for number, line in enumerate(source(path).splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed.append(number)
                continue
            if isinstance(event, dict):
                events.append(event)
            else:
                malformed.append(number)
        return events, malformed

    exported = evidence / "results/paper/batch_summaries"
    if exported.is_dir():
        batches = [{"path": str(exported / name)} for name in (
            "primary-sintef-v19.json", "primary-qwen480-v21.json", "primary-deepseek41-v22.json")]
    else:
        batches = read_json(ANALYSIS / "batch_validation.json")["batches"][:3]

    def resolve_manifest(value: str) -> Path:
        path = Path(value)
        if exported.is_dir():
            candidate = evidence / "results/paper/runs" / path.parent.name / "manifest.json"
            if candidate.is_file():
                return candidate
            raise FileNotFoundError(f"Missing archived run manifest: {candidate}")
        return path if path.is_absolute() else evidence / path
    prices = {}
    for label, path in CONFIGS.items():
        model = next(iter(read_json(ROOT / path)["models"].values()))
        prices[label] = (model["input_price_per_mtok"], model["output_price_per_mtok"])

    rows, tool_evidence, warnings = [], [], []
    for batch_info in batches:
        batch = read_json(Path(batch_info["path"]))
        for run in batch["runs"]:
            if run["method"] not in {"m3", "m4", "m5"}:
                continue
            path = resolve_manifest(run["manifest_path"])
            manifest = read_json(path)
            usage = manifest["usage"]
            label = LABELS[run["model"]]
            row = {
                "model": label, "method": run["method"], "run_id": run["run_id"],
                "split": run["split"], "instance": run["instance"],
                "sample_index": run["sample_index"],
                "recorded_calls": usage["llm_calls"],
                "recorded_total_tokens": usage["total_tokens"],
                "recorded_prompt_tokens": usage["prompt_tokens"],
                "recorded_completion_tokens": usage["completion_tokens"],
                "recorded_cost_usd": usage.get("cost_usd"),
                "executable_valid": int((manifest.get("evaluation") or {}).get("validation", {}).get("overall_status") == "pass"),
            }
            row["standardized_cost_usd"] = (
                (usage["prompt_tokens"] * prices[label][0] + usage["completion_tokens"] * prices[label][1]) / 1e6
                if label in prices else None
            )
            if run["method"] != "m5":
                stages = usage.get("per_stage", [])
                assert len(stages) == usage["llm_calls"]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    assert sum(item["usage"].get(key, 0) for item in stages) == usage[key]
                row["successful_completions"] = usage["llm_calls"]
                rows.append(row)
                continue

            if not (path.parent / "proxy_log.jsonl").is_file():
                raise FileNotFoundError("Full M5 evidence is required; extract the detailed archive first: " + str(path.parent))
            proxy, bad_proxy = jsonl(path.parent / "proxy_log.jsonl")
            trace, bad_trace = jsonl(path.parent / "agent_transcript.jsonl")
            assert not bad_trace, f"Malformed transcript: {path}"
            responses = [event for event in proxy if event.get("event") == "completion"]
            successful = [event for event in responses if event.get("status") == 200]
            accepted = [event for event in trace if event.get("type") == "assistant_message"
                        and event.get("stop_reason") not in {"error", "aborted"}
                        and (event.get("usage") or {}).get("total", 0) > 0]
            steps = [event for event in trace if event.get("type") == "agent_step"]
            assert len(steps) == manifest["agent_steps"]
            assert len(responses) == usage["llm_calls"]
            for key in ("prompt_tokens", "completion_tokens"):
                assert sum((event.get("usage") or {}).get(key, 0) for event in responses) == usage[key]
            provider_costs = [event["usage"]["estimated_cost"] for event in successful
                              if (event.get("usage") or {}).get("estimated_cost") is not None]
            if label in prices:
                assert len(provider_costs) == len(successful)
                assert abs(sum(provider_costs) - usage["cost_usd"]) < 1e-9
            total_sum = sum((event.get("usage") or {}).get("total_tokens", 0) for event in responses)
            gap = bool(bad_proxy or total_sum != usage["total_tokens"] or len(accepted) > len(successful))
            if gap:
                warnings.append({"run_id": run["run_id"], "malformed_proxy_lines": bad_proxy,
                                 "proxy_successes": len(successful), "accepted_assistant_messages": len(accepted),
                                 "recorded_cumulative_tokens": usage["total_tokens"], "surviving_usage_token_sum": total_sum})

            row.update({
                "successful_completions": len(successful),
                "trace_successful_messages": len(accepted),
                # Accepted messages witness a minimum count, not every upstream retry.
                "successful_completions_lower_bound": max(len(successful), len(accepted)),
                "proxy_attempts": len(responses),
                "unsuccessful_responses": len(responses) - len(successful),
                "agent_steps": len(steps), "overrun": int(len(steps) > 12),
                "proxy_log_incomplete": int(gap),
                "cached_input_tokens": sum(((event.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0 for event in responses),
                "step12_inferred_executable_valid": row["executable_valid"],
                "step12_evidence": "run_finished_at_or_before_12",
            })
            if len(steps) > 12:
                boundary = next(index for index, event in enumerate(trace)
                                if event.get("type") == "agent_step" and event.get("step") == 12)
                pending = Counter()
                for event in trace[:boundary + 1]:
                    if event.get("type") == "tool_execution_start":
                        pending[event["tool"]] += 1
                    elif event.get("type") == "tool_execution_end":
                        pending[event["tool"]] -= 1
                assert all(count == 0 for count in pending.values()), f"Pending tool at cutoff: {path}"
                tail = [event for event in trace[boundary + 1:] if event.get("type") == "tool_execution_start"]
                categories = []
                for event in tail:
                    name, arguments = event["tool"], event.get("args") or {}
                    if name in {"read", "grep", "find", "ls"}:
                        category = "read_only"
                    elif name == "bash" and arguments.get("command") == CLEANUP:
                        category = "cleanup_outside_submission"
                    elif name == "bash" and arguments.get("command") == "mkdir -p submission":
                        assert not row["executable_valid"]
                        assert not any((path.parent / "agent_workspace/submission").rglob("*"))
                        category = "empty_submission_directory_only"
                    else:
                        category = "unresolved"
                    tool_evidence.append({"run_id": run["run_id"], "model": label, "category": category,
                                          "timestamp": event.get("ts"), "tool": name, "arguments": arguments})
                    categories.append(category)
                if "unresolved" in categories:
                    row["step12_inferred_executable_valid"] = None
                    row["step12_evidence"] = "unresolved_artifact_effect"
                else:
                    row["step12_evidence"] = ";".join(sorted(set(categories))) or "no_tools_after_12"
            rows.append(row)

    summaries, sensitivity = [], []
    groups = defaultdict(list)
    for row in rows:
        groups[(row["model"], row["method"])].append(row)
    for (model, method), items in sorted(groups.items()):
        assert len(items) == 330
        summary = {"model": model, "method": method, "runs": len(items)}
        for key in ("successful_completions", "recorded_calls", "recorded_total_tokens",
                    "recorded_prompt_tokens", "recorded_completion_tokens", "recorded_cost_usd", "standardized_cost_usd"):
            values = [row[key] for row in items if row.get(key) is not None]
            summary[key + "_mean"] = mean(values) if values else None
        if method == "m5":
            for key in ("successful_completions", "successful_completions_lower_bound", "proxy_attempts", "unsuccessful_responses"):
                summary[key + "_total"] = sum(row[key] for row in items)
                summary[key + "_mean"] = mean(row[key] for row in items)
            summary["incomplete_proxy_logs"] = sum(row["proxy_log_incomplete"] for row in items)
            over = [row for row in items if row["overrun"]]
            unresolved = sum(row["step12_inferred_executable_valid"] is None for row in items)
            sensitivity.append({
                "model": model, "runs": len(items), "overrun_runs": len(over),
                "maximum_steps": max(row["agent_steps"] for row in items),
                "overrun_valid_runs": sum(row["executable_valid"] for row in over),
                "within_limit_valid_runs": sum(row["executable_valid"] for row in items if not row["overrun"]),
                "final_valid_runs": sum(row["executable_valid"] for row in items),
                "step12_inferred_valid_runs": None if unresolved else sum(row["step12_inferred_executable_valid"] for row in items),
                "unresolved_runs": unresolved,
                "post12_tool_categories": dict(Counter(row["step12_evidence"] for row in over)),
            })
        summaries.append(summary)

    args.out.mkdir(parents=True, exist_ok=True)
    def write_csv(name, records):
        fields = list(dict.fromkeys(key for record in records for key in record))
        with (args.out / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    write_csv("run_level.csv", rows)
    write_csv("summary.csv", summaries)
    write_csv("step12_sensitivity.csv", sensitivity)
    report = {"scope": "Saved primary M3-M5 records; no model calls, replay, or source edits",
              "standardized_rates_per_million": prices, "summary": summaries,
              "step12_sensitivity": sensitivity, "post12_tools": tool_evidence,
              "coverage_warnings": warnings, "source_sha256": hashes}
    (args.out / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# M5 accounting and step-limit audit", "",
             "Generated with `python3 -B scripts/audit_m5_accounting.py`. No LLM calls or generated-code execution.", "",
             "## Successful responses and API attempts", "",
             "Successful means HTTP 200 in the saved proxy log; this does not require a valid composition.",
             "Failed responses are operational overhead, not successful completions.", "",
             "| Model | HTTP 200 total | Mean HTTP 200 | Mean recorded attempts | Trace-supported minimum mean | Incomplete logs |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in summaries:
        if row["method"] == "m5":
            lines.append(f"| {row['model']} | {row['successful_completions_total']} | {row['successful_completions_mean']:.5f} | {row['proxy_attempts_mean']:.5f} | {row['successful_completions_lower_bound_mean']:.5f} | {row['incomplete_proxy_logs']} |")
    lines += ["", "Qwen-27B's proxy count is incomplete: one run retains one proxy response but eleven accepted assistant messages. The minimum count uses the larger witness count per run; this does not recover missing upstream retries.", "",
              "## Cost normalization", "", "USD per repetition, using the same frozen input/output rates across methods without cache discounts.",
              "Provider estimates and source manifests remain unchanged; these are not invoices.", "",
              "| Model | Method | Recorded cost | Standardized cost |", "|---|---|---:|---:|"]
    for row in summaries:
        old, new = row["recorded_cost_usd_mean"], row["standardized_cost_usd_mean"]
        lines.append(f"| {row['model']} | {row['method'].upper()} | {old:.6f} | {new:.6f} |" if old is not None else f"| {row['model']} | {row['method'].upper()} | unavailable | unavailable |")
    lines += ["", "## Step-12 artifact sensitivity", "",
              "The cutoff is immediately after the recorded step-12 event (the current turn and its tools have finished). All overrun cutoffs have balanced tool-start/end records; no tool is pending there.",
              "This inspects subsequent tool actions; it does not replay a strict-budget controller or infer a new model trajectory.", "",
              "| Model | Overruns | Maximum steps | Valid overrun runs | All final valid | Inferred valid at step 12 | Unresolved |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in sensitivity:
        lines.append(f"| {row['model']} | {row['overrun_runs']} | {row['maximum_steps']} | {row['overrun_valid_runs']} | {row['final_valid_runs']} | {row['step12_inferred_valid_runs']} | {row['unresolved_runs']} |")
    lines += ["", "After step 12, the only tools are one Qwen-27B cleanup outside submission/, one Qwen-480B read, and one Qwen-480B creation of an empty submission directory. None authors or repairs a submission; the empty-directory run is invalid with or without that directory.",
              "Qwen-27B: 10/64 overrun runs and 44/266 within-threshold runs are valid. All 54 valid submissions were already in place by step 12; inferred validity remains 54/330 (16.36%). This is a trace-based sensitivity conclusion, not a strict-budget experimental result.", "",
              "## Coverage caveat", "", json.dumps(warnings, indent=2), "",
              "All input files are SHA-256 indexed in audit.json. Original records and the manuscript are unchanged."]
    (args.out / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output": str(args.out), "audited_runs": len(rows),
                      "coverage_warnings": warnings, "step12_sensitivity": sensitivity}, indent=2))


if __name__ == "__main__":
    main()
