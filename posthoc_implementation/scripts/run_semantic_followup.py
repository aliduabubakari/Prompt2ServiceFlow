#!/usr/bin/env python3
"""Run isolated, no-LLM follow-up diagnostics on a completed control run.

F1 changes only reviewed public fixtures and replays the reference runtime.
S1 changes only compiled scenario metadata using an explicitly oracle
reference-only counterfactual; this is not a model-facing repair.
A1 mutates saved native outputs to test assertion sensitivity.
R1 replaces only a supported retention service task, leaving all other tasks
as frozen mocks. Nothing here overwrites submitted results or baseline code.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_reference_runtime_controls as controls  # noqa: E402

CONFIG = ROOT / "audit/config/semantic_followup.v2.json"
ADAPTER = ROOT / "audit/retention_adapter.py"
spec = importlib.util.spec_from_file_location("retention_adapter", ADAPTER)
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def sanitize_fixture(node, policy: dict, location=""):
    """Reject unreviewed expectation keys rather than guessing their meaning."""
    changes = []
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            path = f"{location}.{key}" if location else key
            if key.lower().startswith(("expected", "assert")):
                action = policy.get(key)
                if action is None:
                    raise ValueError(f"Unreviewed expectation-like key: {path}")
                changes.append({"key": path, "action": action})
                if action == "remove_private_expectation":
                    continue
                if action != "retain_public_input":
                    raise ValueError("Unknown fixture-field policy")
            cleaned, nested = sanitize_fixture(value, policy, path)
            result[key] = cleaned
            changes.extend(nested)
        return result, changes
    if isinstance(node, list):
        result = []
        for index, item in enumerate(node):
            cleaned, nested = sanitize_fixture(item, policy, f"{location}[{index}]")
            result.append(cleaned)
            changes.extend(nested)
        return result, changes
    return node, changes


def restore_reviewed_inputs(instance: Path, workspace: Path, paths: list, policy: dict) -> list:
    changes = []
    manifest = controls.load(workspace / "workspace.yaml")
    inventory = {item["path"]: item for item in manifest["files"]}
    for relative in paths:
        source = (instance / relative).resolve()
        target = (workspace / relative).resolve()
        if not source.is_relative_to(instance.resolve()) or not target.is_relative_to(workspace.resolve()):
            raise ValueError("Fixture restoration path escapes its root")
        if target.exists():
            raise ValueError("Reviewed restoration unexpectedly targets an existing public file")
        cleaned, field_changes = sanitize_fixture(controls.load(source), policy)
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_text(json.dumps(cleaned, indent=2) + "\n")
        inventory[relative] = {"path": relative, "bytes": target.stat().st_size,
                               "sha256": controls.sha256(target)}
        changes.append({"path": relative, "source_sha256": controls.sha256(source),
                        "derived_sha256": controls.sha256(target), "fields": field_changes})
    # The derived manifest must not claim its amended inputs match the frozen
    # builder's original inventory. Keep removed private fields evaluator-side.
    manifest["files"] = [inventory[k] for k in sorted(inventory)]
    manifest["file_count"] = len(inventory)
    manifest["exclusions"] = [item for item in manifest["exclusions"] if item["path"] not in paths]
    manifest["transforms"].append("diagnostic_v2_reviewed_fixture_fields")
    (workspace / "workspace.yaml").write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return changes


def read_baseline_snapshots(record: dict) -> list[dict]:
    root = Path(record["artifact_directory"]) / "execution"
    results = []
    for entry in json.loads((root / "index.json").read_text()):
        directory = (root / entry["directory"]).resolve()
        if not directory.is_relative_to(root.resolve()):
            raise ValueError("Invalid baseline snapshot directory")
        snapshot = {}
        for relative, expected in entry["artifact_sha256"].items():
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory) or controls.sha256(path) != expected:
                raise ValueError("Baseline snapshot integrity check failed")
            snapshot[relative] = path.read_bytes()
        results.append({"scenario": entry["scenario"], "_snapshot": snapshot,
                        "_errors": entry["execution_errors"],
                        "executed_tasks": entry["executed_tasks"],
                        "skipped_tasks": entry["skipped_tasks"]})
    return results


def corrupt_data(value, protected=False):
    if protected:
        return value
    if isinstance(value, dict):
        return {k: corrupt_data(v, k in {"success", "errors", "status"}) for k, v in value.items()}
    if isinstance(value, list):
        return [corrupt_data(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value + 1000
    if isinstance(value, str):
        return value[::-1] if value != value[::-1] else value + "_changed"
    return value


def flip_success(value):
    if isinstance(value, dict):
        return {k: (not v if k == "success" and isinstance(v, bool) else flip_success(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [flip_success(v) for v in value]
    return value


def mutate(snapshot: dict[str, bytes], mode: str) -> tuple[dict, list]:
    mutated = dict(snapshot)
    changed = []
    for relative, content in snapshot.items():
        if not relative.startswith("artifacts/"):
            continue
        if mode == "delete_artifacts":
            mutated.pop(relative)
            changed.append(relative)
            continue
        if relative.endswith(".json"):
            try:
                value = json.loads(content)
            except (ValueError, UnicodeDecodeError):
                continue
            if mode == "successful_status_only":
                revised = {"success": True, "errors": []}
            elif mode == "corrupt_data_keep_status":
                revised = corrupt_data(value)
            elif mode == "flip_success":
                revised = flip_success(value)
            else:
                raise ValueError("Unknown mutation")
            if revised != value:
                mutated[relative] = (json.dumps(revised) + "\n").encode()
                changed.append(relative)
        elif mode == "successful_status_only":
            mutated.pop(relative)
            changed.append(relative)
        elif mode == "corrupt_data_keep_status" and relative.endswith(".csv"):
            table = list(csv.reader(io.StringIO(content.decode())))
            if len(table) > 1:
                altered = [table[0]] + [[str(corrupt_data(v)) for v in row] for row in table[1:]]
                stream = io.StringIO()
                csv.writer(stream).writerows(altered)
                mutated[relative] = stream.getvalue().encode()
                changed.append(relative)
    return mutated, changed


def assertion_mutations(instance: Path, baseline_record: dict, output: Path, modes: list) -> dict:
    results = read_baseline_snapshots(baseline_record)
    assertions = controls.load(instance / "gold/assertions.yaml")
    original = controls.evaluate_native(results, assertions)
    if original["overall_status"] != "pass":
        raise ValueError("Native baseline snapshots no longer reproduce their positive control")
    reports = {}
    for mode in modes:
        variants = []
        changes = {}
        for item in results:
            revised = dict(item)
            revised["_snapshot"], paths = mutate(item["_snapshot"], mode)
            changes[item["scenario"]] = paths
            variants.append(revised)
        count = sum(len(paths) for paths in changes.values())
        evaluation = controls.evaluate_native(variants, assertions)
        controls.persist_snapshots(variants, output / mode / "execution")
        reports[mode] = {"changed_files": count, "changed_paths": changes,
                         "applicability": "applicable" if count else "no_mutation_possible",
                         "detected": evaluation["overall_status"] != "pass" if count else None,
                         "g6_assert": evaluation,
                         "qualification": "Output mutation diagnostic; no claim of schema conformance or valid changed-input expected values."}
    return {"status": "completed", "baseline_snapshot_reproduced": True, "mutations": reports}


def score_and_capture(instance: Path, workspace: Path, submission: Path, output: Path) -> dict:
    execute = controls.scoring._execute_scenarios
    captured = []

    def observe(*args, **kwargs):
        result = execute(*args, **kwargs)
        captured.extend(controls.persist_snapshots(result, output / "execution"))
        return result

    with patch.object(controls.scoring, "_execute_scenarios", side_effect=observe):
        report = controls.scoring._score_g6_assert(instance, workspace, submission)
    if report.get("status") == "unscored":
        raise ValueError(report.get("reason", "Assertion evaluation unavailable"))
    return {"g6_assert": report, "assertion_status": report.get("overall_status"),
            "execution_status": "pass" if captured and all(not x["execution_errors"] for x in captured) else "fail",
            "public_validity": "not_measured_in_followup", "execution": captured}


def retention_specs(submission: Path, workspace: Path) -> list[dict]:
    ir = controls.load(submission / "serviceflow.yaml")
    artifacts = {item["artifact_id"]: item for item in ir["artifacts"]}
    specs = []
    for binding in ir["bindings"]:
        if (binding["service_id"], binding["service_version"]) != retention.SERVICE:
            continue
        inputs = {}
        for item in binding.get("input_bindings", []):
            artifact = artifacts[item["artifact_id"]]
            inputs[item["port"]] = {"artifact_id": item["artifact_id"],
                                    "fixture_ref": artifact.get("fixture_ref"),
                                    "upstream": artifact["producer"] is not None}
        outputs = []
        for item in binding.get("output_bindings", []):
            artifact = artifacts[item["artifact_id"]]
            output = {"port": item["port"], "artifact_id": item["artifact_id"]}
            if artifact.get("schema_ref"):
                path = (workspace / artifact["schema_ref"]).resolve()
                if not path.is_relative_to(workspace.resolve()):
                    raise ValueError("Output schema escapes public workspace")
                output["schema"] = controls.load(path)
            outputs.append(output)
        specs.append({"intent_id": binding["intent_id"], "parameters": binding["parameter_bindings"],
                      "inputs": inputs, "outputs": outputs})
    return specs


def install_retention(submission: Path, specs: list[dict]) -> None:
    manifest = controls.load(submission / "runtime/manifest.yaml")
    shutil.copy2(ADAPTER, submission / "runtime/scripts/_retention_adapter.py")
    by_id = {item["intent_id"]: item for item in specs}
    for task in manifest["tasks"]:
        if task["intent_id"] not in by_id:
            continue
        payload = json.dumps(by_id[task["intent_id"]], sort_keys=True)
        path = submission / "runtime" / task["script"]
        path.write_text(
            '"""Diagnostic retention service adapter, other tasks remain frozen mocks."""\n'
            'import argparse, json\nfrom pathlib import Path\nfrom _retention_adapter import run\n'
            'parser=argparse.ArgumentParser()\n'
            'parser.add_argument("--workspace",type=Path,required=True)\n'
            'parser.add_argument("--fixtures",type=Path,required=True)\n'
            'args=parser.parse_args()\n'
            f'run(json.loads({payload!r}), args.workspace, args.fixtures)\n'
        )


def retention_input_probe(submission: Path, workspace: Path, specs: list[dict], output: Path) -> dict:
    """Change a public input and execute only the supported service task.

    This is an isolated service-contract check, not a whole-pipeline outcome;
    original hidden assertions must not be applied to changed inputs.
    """
    if len(specs) != 1:
        return {"status": "not_applicable", "reason": "Probe currently requires one retention invocation"}
    service = specs[0]
    bound = service["inputs"].get("runtime_parameters")
    if not bound or bound.get("upstream") or not bound.get("fixture_ref"):
        return {"status": "not_applicable", "reason": "Probe requires an explicit external public parameter fixture"}
    with tempfile.TemporaryDirectory(prefix="p2sf-retention-input-probe-") as temporary:
        instance = Path(temporary) / "instance"
        instance.mkdir()
        shutil.copytree(submission / "runtime", instance / "runtime")
        shutil.copytree(workspace / "fixtures", instance / "fixtures")
        name = service["parameters"]["max_age_parameter_name"]
        manifest = controls.load(instance / "runtime/manifest.yaml")
        changes = {}
        for scenario in manifest["scenarios"]:
            conventional = instance / "fixtures/scenarios" / scenario["name"]
            fixture_root = instance / scenario["fixture_root"] if scenario.get("fixture_root") else (
                conventional if conventional.is_dir() else instance / "fixtures/inputs")
            fixture = (fixture_root / retention.fixture_relative(bound["fixture_ref"])).resolve()
            if not fixture.is_relative_to((instance / "fixtures").resolve()):
                raise ValueError("Probe fixture escapes public fixture directory")
            values = json.loads(fixture.read_text())
            previous = values.get(name, service["parameters"]["default_max_age_days"])
            if isinstance(previous, bool) or not isinstance(previous, int):
                raise ValueError("Probe parameter must be integer")
            # Distinct scenarios may intentionally share one input file. Reuse
            # its single perturbation rather than incrementing it repeatedly.
            existing = next((item for item in changes.values() if item["path"] == str(fixture)), None)
            changed = existing["changed_input"] if existing else previous + 7
            values[name] = changed
            fixture.write_text(json.dumps(values) + "\n")
            changes[scenario["name"]] = {"path": str(fixture),
                "original_input": existing["original_input"] if existing else previous,
                "changed_input": changed}
        manifest["tasks"] = [t for t in manifest["tasks"] if t["intent_id"] == service["intent_id"]]
        for task in manifest["tasks"]:
            for field in ("dependencies", "depends", "when", "local_condition"):
                task.pop(field, None)
        result = controls._execute_scenarios(instance, manifest, sandbox_generated=True)
        controls.persist_snapshots(result, output / "execution")
        artifact = next(item["artifact_id"] for item in service["outputs"] if item["port"] == "retention_config")
        observed = []
        for scenario in result:
            data = scenario["_snapshot"].get(f"artifacts/{artifact}.json")
            actual = json.loads(data).get("max_age_days") if data else None
            changed = changes[scenario["scenario"]]["changed_input"]
            observed.append({"scenario": scenario["scenario"], "actual_max_age_days": actual,
                             "execution_errors": scenario["_errors"],
                             "pass": actual == changed and not scenario["_errors"]})
        return {"status": "completed", "input_parameter": name, "input_changes": changes,
                "observed": observed,
                "input_consumption_pass": bool(observed) and all(item["pass"] for item in observed),
                "original_hidden_assertions_used": False,
                "qualification": "Isolated service invocation; other pipeline operations and branch obligations are not tested."}


def run_condition(name: str, case: str, baseline: dict, workspace_source: Path,
                  output: Path, policy: dict) -> dict:
    output.mkdir(exist_ok=False, parents=True)
    instance = controls.BENCHMARK / "instances" / case
    prior = baseline["results"][case]
    if name == "a1_assertion_mutations":
        return assertion_mutations(instance, prior[controls.CONDITIONS[0]], output, policy["mutation_modes"])
    if name == "f1_reviewed_fixture_replay" and case not in policy["fixture_restorations"]:
        return {"status": "not_applicable", "reason": "No reviewed fixture restoration for this case"}
    mismatch = prior[controls.CONDITIONS[2]].get("g6_assert", {})
    if name == "s1_reference_scenario_counterfactual" and not (
        mismatch.get("unmatched_execution_scenarios") or mismatch.get("unmatched_assertion_scenarios")
    ):
        return {"status": "not_applicable", "reason": "No baseline scenario mismatch"}
    if name == "r1_retention_service_execution":
        reference = controls.load(instance / "gold/serviceflow.yaml")
        if not any((item["service_id"], item["service_version"]) == retention.SERVICE
                   for item in reference["bindings"]):
            return {"status": "not_applicable", "reason": "No supported retention service binding"}
    workspace = output / "public_workspace"
    shutil.copytree(workspace_source, workspace, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    submission = output / "submission"
    controls.stage_ir(instance, workspace, submission)
    baseline_condition = controls.CONDITIONS[1] if name == "f1_reviewed_fixture_replay" else controls.CONDITIONS[2]
    record = {"status": "completed", "generated_method_result": False,
              "baseline_assertion_status": prior[baseline_condition]["assertion_status"]}
    if name == "f1_reviewed_fixture_replay":
        record["fixture_changes"] = restore_reviewed_inputs(
            instance, workspace, policy["fixture_restorations"][case], policy["reviewed_fixture_keys"])
        shutil.copytree(instance / "runtime", submission / "runtime", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        record["compared_to"] = "c1_reference_staged"
    else:
        controls.materialize_runtime(workspace, submission)
        record["compared_to"] = "c2_reference_ir_compiled"
        if name == "s1_reference_scenario_counterfactual":
            generated = controls.load(submission / "runtime/manifest.yaml")
            reference = controls.load(instance / "runtime/manifest.yaml")
            record["original_scenarios"] = generated["scenarios"]
            generated["scenarios"] = copy.deepcopy(reference["scenarios"])
            generated["workflow_parameters"] = copy.deepcopy(reference.get("workflow_parameters", []))
            (submission / "runtime/manifest.yaml").write_text(controls.yaml.safe_dump(generated, sort_keys=False))
            record["reference_only_oracle_scenarios"] = True
            record["qualification"] = policy["scenario_condition_role"]
        elif name == "r1_retention_service_execution":
            specs = retention_specs(submission, workspace)
            if not specs:
                return {"status": "not_applicable", "reason": "No supported retention service binding"}
            install_retention(submission, specs)
            controls.write_json(output / "adapter_specs.json", specs)
            tasks = controls.load(submission / "runtime/manifest.yaml")["tasks"]
            record["adapter_tasks"] = len(specs)
            record["remaining_mock_tasks"] = len(tasks) - len(specs)
            record["qualification"] = policy["retention_condition_role"]
        else:
            raise ValueError("Unknown follow-up condition")
    record.update(score_and_capture(instance, workspace, submission, output))
    if name == "r1_retention_service_execution":
        record["changed_input_probe"] = retention_input_probe(
            submission, workspace, specs, output / "changed_input_probe")
    return record


def render(run: dict) -> str:
    lines = ["# Semantic follow-up diagnostics", "",
             "No new model inference. Conditions isolate different changes and must not be pooled as a new method score.", "",
             "| Pipeline | Condition | State | G6-Assert |", "|---|---|---|---|"]
    totals = Counter()
    for case, conditions in run["results"].items():
        for name, record in conditions.items():
            totals[(name, record["status"])] += 1
            lines.append(f"| {case} | {name} | {record['status']} | {record.get('assertion_status', 'see mutations')} |")
    lines += ["", "## Condition coverage", ""]
    for (condition, status), count in sorted(totals.items()):
        lines.append(f"- {condition}: {status} = {count}")
    mutation_counts = Counter()
    for conditions in run["results"].values():
        for mode, result in conditions.get("a1_assertion_mutations", {}).get("mutations", {}).items():
            state = "not applicable" if result["detected"] is None else "detected" if result["detected"] else "survived"
            mutation_counts[(mode, state)] += 1
    if mutation_counts:
        lines += ["", "## Assertion-mutation sensitivity", ""]
        for (mode, state), count in sorted(mutation_counts.items()):
            lines.append(f"- {mode}: {state} = {count}")
    lines += ["", "Scenario alignment is an oracle reference-only diagnostic, not a public-input correction.",
              "Retention coverage is partial; unsupported service tasks remain mocks.",
              "Surviving output mutations identify tests to review, not independently proven semantic errors.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-run", type=Path, help="Completed v1 control-run directory")
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--all", action="store_true", help="Select all cases present in the baseline control run")
    select.add_argument("--instances", nargs="+")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.resume and (args.control_run or args.all or args.instances):
        parser.error("Resume restores the original selection; do not supply baseline or selection flags")
    previous = controls.load(args.resume / "run.json") if args.resume else None
    baseline_root = Path(previous["baseline_directory"]) if previous else args.control_run
    if baseline_root is None:
        parser.error("Provide --control-run with the completed control directory")
    baseline_root = baseline_root.resolve()
    baseline_path = baseline_root / "run.json"
    baseline = controls.load(baseline_path)
    if baseline["status"] != "complete" or not baseline.get("source_inputs_unchanged"):
        raise ValueError("Baseline controls are incomplete or have changed inputs")
    policy = controls.load(CONFIG)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != policy["baseline_commit"] or baseline["baseline_commit"] != head:
        raise ValueError("Published baseline commit does not match this protocol")
    cases = previous["cases"] if previous else (
        args.instances or [f"{c['split']}/{c['instance']}" for c in (
            baseline["cases"] if args.all else controls.load(controls.CONFIG)["cases"])])
    if len(set(cases)) != len(cases) or any(case not in baseline["results"] for case in cases):
        raise ValueError("Duplicate selection or a selected case missing from baseline controls")
    if args.dry_run:
        print(json.dumps({"protocol_version": policy["protocol_version"], "cases": cases,
                          "conditions": policy["conditions"], "llm_calls": 0}, indent=2))
        return 0
    if os.environ.get("P2SF_OUTER_SANDBOX") == "1":
        raise ValueError("Unset P2SF_OUTER_SANDBOX; normal sandbox execution is required")
    if controls.platform.system() == "Darwin" and not shutil.which("sandbox-exec"):
        raise ValueError("macOS sandbox-exec unavailable")
    hashes = controls.input_hashes()
    if controls.fingerprint(hashes) != baseline["input_fingerprint"]:
        raise ValueError("Frozen v1 code/data no longer match the selected baseline run")
    for path in (CONFIG, ADAPTER, Path(__file__).resolve(), baseline_path):
        hashes[str(path.resolve())] = controls.sha256(path)
    environment = controls.environment()
    if environment != baseline["environment"]:
        raise ValueError("Environment differs from the control baseline; review before comparison")
    if previous:
        if previous["input_fingerprint"] != controls.fingerprint(hashes):
            raise ValueError("Follow-up inputs changed; start a new versioned run")
        output = args.resume.resolve()
        run = previous
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = ROOT / "audit/outputs" / f"followup_v2__{stamp}__{uuid.uuid4().hex[:8]}"
        output.mkdir(parents=True, exist_ok=False)
        controls.write_json(output / "input_sha256.json", hashes)
        for path in (CONFIG, ADAPTER, Path(__file__).resolve()):
            shutil.copy2(path, output / path.name)
        run = {"protocol_version": policy["protocol_version"], "baseline_directory": str(baseline_root),
               "input_fingerprint": controls.fingerprint(hashes), "environment": environment,
               "cases": cases, "conditions": policy["conditions"], "llm_calls": 0, "results": {}}
    print(f"Output: {output}", flush=True)
    run["status"] = "running"
    controls.write_json(output / "run.json", run)
    for case in cases:
        workspace = baseline_root / "cases" / case / "public_workspace" / case
        if not (workspace / "workspace.yaml").is_file():
            raise ValueError(f"Missing baseline public workspace: {case}")
        records = run["results"].setdefault(case, {})
        for condition in policy["conditions"]:
            if condition in records:
                continue
            attempt = output / "cases" / case / condition / ("attempt_" + uuid.uuid4().hex[:8])
            print(f"Running {case} {condition}", flush=True)
            try:
                record = run_condition(condition, case, baseline, workspace, attempt, policy)
            except Exception as exc:
                record = {"status": "error", "error_type": type(exc).__name__, "error": str(exc)}
            record["artifact_directory"] = str(attempt)
            controls.write_json(attempt / "condition.json", record)
            records[condition] = record
            controls.write_json(output / "run.json", run)
            (output / "summary.md").write_text(render(run))
            print(f"  {record['status']} assertions={record.get('assertion_status', 'see mutation reports')}", flush=True)
    unchanged = controls.input_hashes() == {k: v for k, v in hashes.items() if not Path(k).is_absolute()}
    unchanged = unchanged and all(controls.sha256(Path(k)) == v for k, v in hashes.items() if Path(k).is_absolute())
    run["source_inputs_unchanged"] = unchanged
    run["status"] = "complete" if unchanged and all(
        record["status"] != "error" for records in run["results"].values() for record in records.values()
    ) else "complete_with_errors"
    controls.write_json(output / "run.json", run)
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
