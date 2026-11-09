#!/usr/bin/env python3
"""Compare reference execution with the frozen submission/compiler paths.

No LLM client is constructed. Baseline implementation files are imported from
this isolated checkout and never edited. All three execution paths use the
frozen network-disabled sandbox. Gold IR is an evaluation-side positive
control, never a generated-method result.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402
from prompt2serviceflow.experiments import scoring  # noqa: E402
from prompt2serviceflow.experiments.runtime_compiler import (  # noqa: E402
    RUNTIME_COMPILER_VERSION, materialize_runtime,
)
from prompt2serviceflow.experiments.workspace import build_workspace  # noqa: E402
from prompt2serviceflow.validators.instance_validation import (  # noqa: E402
    _evaluate_assertion, _execute_scenarios, _restore_snapshot,
)

BENCHMARK = ROOT / "benchmark"
CONFIG = ROOT / "audit/config/reference_controls.v1.json"
CONDITIONS = ("c0_reference_native", "c1_reference_staged", "c2_reference_ir_compiled")


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def choose_cases(protocol: dict, requested: list[str] | None, all_cases: bool) -> list[dict]:
    if all_cases:
        return [{"split": p.parent.name, "instance": p.name, "reason": "Full corpus"}
                for split in ("main", "validation", "extension")
                for p in sorted((BENCHMARK / "instances" / split).iterdir()) if p.is_dir()]
    if not requested:
        return protocol["cases"]
    cases = []
    for identity in requested:
        parts = identity.split("/")
        if len(parts) != 2 or parts[0] not in {"main", "validation", "extension"}:
            raise ValueError("Use explicit case identities such as main/airflow_db_cleanup")
        if not parts[1] or Path(parts[1]).name != parts[1] or parts[1] in {".", ".."}:
            raise ValueError("Invalid instance name")
        cases.append({"split": parts[0], "instance": parts[1], "reason": "Explicit CLI selection"})
    if len({(c["split"], c["instance"]) for c in cases}) != len(cases):
        raise ValueError("Duplicate case selection")
    return cases


def input_hashes() -> dict[str, str]:
    # Hash the whole read-only benchmark, not only the IR: fixtures, catalog
    # pins, schemas, assertions, and source descriptions can all affect results.
    paths = [ROOT / "pyproject.toml", CONFIG, Path(__file__).resolve()]
    for directory in (ROOT / "src", ROOT / "schemas", BENCHMARK,
                      ROOT / "experiments/tools/bin"):
        paths.extend(p for p in directory.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(set(paths))}


def fingerprint(hashes: dict) -> str:
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def environment() -> dict:
    packages = {}
    for name in ("PyYAML", "jsonschema", "pydantic", "openai"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {"python": sys.version, "executable": sys.executable,
            "platform": platform.platform(), "packages": packages,
            "sandbox": "macOS Seatbelt" if platform.system() == "Darwin" else "Docker",
            "scorer_version": scoring.TOOL_VERSION,
            "runtime_compiler_version": RUNTIME_COMPILER_VERSION}


def persist_snapshots(results: list[dict], destination: Path) -> list[dict]:
    """Keep actual produced bytes before the frozen scorer consumes snapshots."""
    if destination.exists():
        raise ValueError(f"Snapshot target already exists: {destination}")
    destination.mkdir(parents=True)
    index = []
    for number, result in enumerate(results):
        folder = destination / f"scenario_{number:03d}"
        folder.mkdir()
        artifact_hashes = {}
        for relative, content in result["_snapshot"].items():
            path = (folder / relative).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError("Snapshot path escapes destination")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            artifact_hashes[relative] = hashlib.sha256(content).hexdigest()
        index.append({"scenario": result["scenario"], "directory": folder.name,
                      "executed_tasks": result.get("executed_tasks", []),
                      "skipped_tasks": result.get("skipped_tasks", []),
                      "execution_errors": result["_errors"], "artifact_sha256": artifact_hashes})
    write_json(destination / "index.json", index)
    return index


def evaluate_native(results: list[dict], assertions: dict) -> dict:
    """Strict name matching for the native reference path, without alias repair.

    This independent aggregation uses the frozen per-assertion evaluator. It
    is a reference control, not a revision of the published submission scorer.
    Duplicate or empty tests must never become a vacuous positive control.
    """
    sets = {}
    for item in assertions["scenarios"]:
        if item["scenario"] in sets:
            raise ValueError("Duplicate reference assertion scenario")
        ids = [a["assertion_id"] for a in item["assertions"]]
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError("Duplicate or empty reference assertion set")
        sets[item["scenario"]] = item["assertions"]
    execution_names = [item["scenario"] for item in results]
    if len(execution_names) != len(set(execution_names)):
        raise ValueError("Duplicate execution scenario")
    scenarios = []
    passed = 0
    for result in results:
        checks = []
        with tempfile.TemporaryDirectory(prefix="p2sf-native-assert-") as temporary:
            output = Path(temporary)
            _restore_snapshot(result["_snapshot"], output)
            for assertion in sets.get(result["scenario"], []):
                if result["_errors"]:
                    status, message = "error", "scenario execution failed"
                else:
                    try:
                        ok, message = _evaluate_assertion(assertion, output)
                        status = "pass" if ok else "fail"
                    except Exception as exc:
                        status, message = "error", f"assertion evaluation error: {exc}"
                passed += int(status == "pass")
                checks.append({"assertion_id": assertion["assertion_id"],
                               "status": status, "message": message})
        scenarios.append({"scenario": result["scenario"], "assertions": checks,
                          "execution_errors": result["_errors"],
                          "status": "pass" if checks and not result["_errors"] and
                          all(a["status"] == "pass" for a in checks) else "fail"})
    expected = sum(len(value) for value in sets.values())
    return {"overall_status": "pass" if scenarios and expected and
            set(execution_names) == set(sets) and
            all(s["status"] == "pass" for s in scenarios) else "fail",
            "scenarios": scenarios, "assertions_total": expected,
            "assertions_passed": passed, "pass_rate": passed / expected if expected else None,
            "unmatched_execution_scenarios": sorted(set(execution_names) - set(sets)),
            "unmatched_assertion_scenarios": sorted(set(sets) - set(execution_names))}


def stage_ir(instance: Path, workspace: Path, destination: Path) -> list[str]:
    """Adapt only public metadata, never bindings/parameters/output identities."""
    destination.mkdir(parents=True)
    document = copy.deepcopy(load(instance / "gold/serviceflow.yaml"))
    changes = []
    for field in ("internal_spec_path", "internal_spec_sha256"):
        if field in document["source"]:
            document["source"].pop(field)
            changes.append(f"removed private source.{field}")
    pin = load(workspace / "workspace.yaml")["catalog"]
    document["catalog_snapshot"] = {"catalog_id": "serviceflow_catalog", "version": pin["version"],
                                    "sha256": pin["sanitized_catalog_yaml_sha256"]}
    changes.append("replaced catalog metadata hash with sanitized workspace catalog pin")
    (destination / "serviceflow.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    write_json(destination / "staging_changes.json", changes)
    return changes


def run_condition(condition: str, instance: Path, workspace: Path, attempt: Path) -> dict:
    attempt.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    record = {"condition": condition, "status": "completed", "kind": "reference_control",
              "generated_method_result": False}
    try:
        if condition == CONDITIONS[0]:
            # Copy only runtime/public data to a temporary root. Private
            # assertions remain outside the sandbox and are read evaluator-side.
            with tempfile.TemporaryDirectory(prefix="p2sf-native-reference-") as temporary:
                native = Path(temporary) / "instance"
                native.mkdir()
                for name in ("runtime", "fixtures", "contracts"):
                    if (instance / name).is_dir():
                        shutil.copytree(instance / name, native / name,
                                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                manifest = load(native / "runtime/manifest.yaml")
                results = _execute_scenarios(native, manifest, sandbox_generated=True)
                record["execution"] = persist_snapshots(results, attempt / "execution")
                record["g6_assert"] = evaluate_native(results, load(instance / "gold/assertions.yaml"))
            record["public_validation"] = "not_applicable_native_reference_control"
        else:
            submission = attempt / "submission"
            record["staging_changes"] = stage_ir(instance, workspace, submission)
            if condition == CONDITIONS[1]:
                shutil.copytree(instance / "runtime", submission / "runtime",
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                materialize_runtime(workspace, submission)
            # Capture the scorer's actual scenario outputs without re-executing
            # them or changing scorer logic. The observer patch is local to this
            # sequential invocation; baseline source is left byte-identical.
            execute = scoring._execute_scenarios

            def capture(*args, **kwargs):
                results = execute(*args, **kwargs)
                record["execution"] = persist_snapshots(results, attempt / "execution")
                return results

            with patch.object(scoring, "_execute_scenarios", side_effect=capture):
                report = scoring.score_submission(instance, workspace, submission)
            write_json(attempt / "score.json", report)
            record["g6_assert"] = report["g6_assert"]
            record["public_validation"] = report["public_gates"]["overall_status"]
            record["first_failing_gate"] = report["public_gates"]["first_failing_gate"]
            record["full_public_and_assertion_pass"] = report["summary"]["full_pass_g0_g6"]
            if report["g6_assert"].get("status") == "unscored":
                record.update(status="error", error_type="ScoringUnavailable",
                              error=report["g6_assert"].get("reason", "No assertion score produced"))
        errors = [error for scenario in record.get("execution", [])
                  for error in scenario["execution_errors"]]
        record["execution_status"] = "pass" if record.get("execution") and not errors else "fail"
        record["execution_errors"] = errors
    except Exception as exc:
        record.update(status="error", error_type=type(exc).__name__, error=str(exc))
    record["elapsed_seconds"] = round(time.monotonic() - start, 3)
    record["assertion_status"] = record.get("g6_assert", {}).get("overall_status",
                                    record.get("g6_assert", {}).get("status", "not_scored"))
    record["artifact_directory"] = str(attempt)
    write_json(attempt / "control.json", record)
    return record


def summary_text(results: dict) -> str:
    lines = ["# Reference runtime/compiler controls", "",
             "Diagnostic reference controls only; no LLM inference or changed publication results.", "",
             "| Pipeline | Control | Execution | G6-Assert | Public gates |",
             "|---|---|---|---|---|"]
    for identity, conditions in results.items():
        for name, record in conditions.items():
            lines.append(f"| {identity} | {name} | {record.get('execution_status', record['status'])} | "
                         f"{record['assertion_status']} | {record.get('public_validation', 'error')} |")
    lines += ["", "Interpretation: if native and staged references pass but compiled reference IR fails,",
              "the runtime/compiler path loses semantics even without LLM generation. Native versus",
              "staged differences require fixture/metadata/assembly review. Reference passes alone",
              "do not prove task correctness on new inputs; mutation/input-dependence controls follow.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--instances", nargs="+", metavar="SPLIT/INSTANCE")
    selection.add_argument("--all", action="store_true", help="Use all 110 reference pipelines")
    parser.add_argument("--dry-run", action="store_true", help="Show selection; do not execute or write outputs")
    parser.add_argument("--resume", type=Path, help="Resume a previous output directory with identical inputs")
    parser.add_argument("--output", type=Path, help="New output directory; must not already exist")
    parser.add_argument("--retry-errors", action="store_true", help="On resume, retry error records in new attempt directories")
    args = parser.parse_args()
    if args.resume and (args.output or args.instances or args.all):
        parser.error("--resume restores the recorded selection; do not combine it with output/selection flags")
    protocol = load(CONFIG)
    prior = None
    if args.resume:
        prior = load(args.resume / "run.json")
        cases = prior["cases"]
    else:
        cases = choose_cases(protocol, args.instances, args.all)
    if not cases:
        raise ValueError("No reference pipelines selected")
    for case in cases:
        instance = BENCHMARK / "instances" / case["split"] / case["instance"]
        for required in ("gold/serviceflow.yaml", "gold/assertions.yaml", "runtime/manifest.yaml"):
            if not (instance / required).is_file():
                raise ValueError(f"Missing required reference input: {instance / required}")
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if baseline != protocol["baseline_commit"]:
        raise ValueError("This protocol requires the recorded published HEAD; version a new protocol before rebasing")
    protected = ("src", "benchmark", "schemas", "experiments/tools/bin")
    if subprocess.check_output(["git", "diff", "HEAD", "--", *protected], cwd=ROOT):
        raise ValueError("Frozen implementation/data have local changes; use a new protocol version")
    if args.dry_run:
        print(json.dumps({"baseline_commit": baseline, "conditions": CONDITIONS, "cases": cases,
                          "llm_calls": 0}, indent=2))
        return 0
    import os
    if os.environ.get("P2SF_OUTER_SANDBOX") == "1":
        raise ValueError("Unset P2SF_OUTER_SANDBOX; this diagnostic requires the normal sandbox")
    if platform.system() == "Darwin" and not shutil.which("sandbox-exec"):
        raise ValueError("macOS sandbox-exec is unavailable")
    hashes = input_hashes()
    env = environment()
    if prior:
        if prior["input_fingerprint"] != fingerprint(hashes) or prior["environment"] != env:
            raise ValueError("Inputs or environment differ; preserve the old run and start a new one")
        output = args.resume.resolve()
        run = prior
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = (args.output or ROOT / "audit/outputs" / f"controls__{stamp}__{uuid.uuid4().hex[:8]}").resolve()
        output.mkdir(parents=True, exist_ok=False)
        write_json(output / "input_sha256.json", hashes)
        run = {"protocol_version": protocol["protocol_version"], "baseline_commit": baseline,
               "input_fingerprint": fingerprint(hashes), "environment": env,
               "started_at": datetime.now(timezone.utc).isoformat(), "cases": cases,
               "conditions": CONDITIONS, "llm_calls": 0, "results": {}}
    print(f"Output: {output}", flush=True)
    run["status"] = "running"
    write_json(output / "run.json", run)
    for case in cases:
        identity = f"{case['split']}/{case['instance']}"
        instance = BENCHMARK / "instances" / identity
        results = run["results"].setdefault(identity, {})
        case_root = output / "cases" / identity
        workspace_root = case_root / "public_workspace"
        workspace = workspace_root / identity
        if not (workspace / "workspace.yaml").is_file():
            build_workspace(instance, workspace_root, split=case["split"], benchmark_root=BENCHMARK)
        for condition in CONDITIONS:
            if condition in results and not (args.retry_errors and results[condition]["status"] == "error"):
                continue
            attempt = case_root / condition / f"attempt_{uuid.uuid4().hex[:10]}"
            print(f"Running {identity} {condition}", flush=True)
            results[condition] = run_condition(condition, instance, workspace, attempt)
            result = results[condition]
            print(f"  status={result['status']} execution={result.get('execution_status')} "
                  f"assertions={result['assertion_status']}", flush=True)
            write_json(output / "run.json", run)
            (output / "summary.md").write_text(summary_text(run["results"]))
    # Input bytes must still match after sandboxed execution and staging.
    unchanged = hashes == input_hashes()
    run["source_inputs_unchanged"] = unchanged
    run["condition_status_counts"] = dict(Counter(
        record["status"] for conditions in run["results"].values() for record in conditions.values()))
    run["status"] = "complete" if unchanged and not run["condition_status_counts"].get("error") else "complete_with_errors"
    run["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "run.json", run)
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
