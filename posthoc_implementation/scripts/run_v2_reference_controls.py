#!/usr/bin/env python3
"""V2 candidate reference regression controls; no model inference or broad replay."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "audit"))
sys.path.insert(0, str(ROOT / "audit/v2"))
import run_executor_replay as replay
import service_executor as executor
import public_bindings

controls = replay.controls
CONFIG = ROOT / "audit/v2/reference_controls.json"
TESTS = ROOT / "tests/unit/test_v2_reference_controls.py"
IMPLEMENTATION = [Path(__file__).resolve(), CONFIG, TESTS,
                  ROOT / "audit/v2/service_executor.py", ROOT / "audit/v2/public_bindings.py",
                  ROOT / "audit/v2/PUBLIC_EXECUTION_CONTRACT.md",
                  ROOT / "audit/service_executor_v3.py", ROOT / "audit/retention_adapter.py",
                  ROOT / "scripts/run_executor_replay.py"]


def install_v2(spec: dict, destination: Path, fixtures: Path, scenarios: list) -> dict:
    scripts = destination / "runtime/scripts"
    scripts.mkdir(parents=True)
    for source in (ROOT / "audit/v2/service_executor.py", ROOT / "audit/service_executor_v3.py",
                   ROOT / "audit/retention_adapter.py"):
        shutil.copy2(source, scripts / source.name)
    controls.write_json(scripts / "spec.json", spec)
    (scripts / "invoke.py").write_text(
        'import argparse,json,csv\nfrom pathlib import Path\nfrom service_executor import run,UnsupportedOperation\n'
        'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path)\n'
        'a=p.parse_args()\n'
        'try:\n run(json.loads(Path(__file__).with_name("spec.json").read_text()),a.workspace,a.fixtures)\n'
        'except UnsupportedOperation as e:\n print("UNSUPPORTED_OPERATION:",e);raise SystemExit(3)\n'
        'except (ValueError,KeyError,OSError,TypeError,csv.Error) as e:\n print("INVOCATION_REJECTED:",e);raise SystemExit(2)\n')
    shutil.copytree(fixtures, destination / "fixtures")
    manifest = {"runtime_manifest_version": "0.1.0", "pipeline_id": "v2_reference_service_control",
                "image": "python:3.12-slim", "workflow_parameters": [],
                "tasks": [{"intent_id": executor.identifier(spec["intent_id"]), "script": "scripts/invoke.py",
                           "arguments": ["--workspace", "{workspace}", "--fixtures", "{fixtures}"], "retries": 0}],
                "scenarios": scenarios}
    (destination / "runtime/manifest.yaml").write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def check_paths(output: Path) -> list[dict]:
    checks = []
    for label in ("base_execution", "changed_execution"):
        directory = output / label
        if not (directory / "index.json").is_file():
            checks.append({"condition": label, "pass": False, "error": "No execution snapshots"})
            continue
        for scenario in replay.read_json(directory / "index.json"):
            snapshot = executor.inside(directory, scenario["directory"])
            mapping_path = snapshot / "logs/public_output_bindings.json"
            try:
                mappings = replay.read_json(mapping_path)
                if mappings["contract_version"] != executor.CONTRACT_VERSION:
                    raise ValueError("Wrong output contract version")
                for item in mappings["outputs"]:
                    canonical = executor.inside(snapshot, item["canonical_path"])
                    if controls.sha256(canonical) != item["sha256"]:
                        raise ValueError("Canonical output hash mismatch")
                    if item.get("materialized_path"):
                        requested = executor.inside(snapshot, item["materialized_path"])
                        if controls.sha256(requested) != item["sha256"] or requested == canonical:
                            raise ValueError("Requested output is not a separate byte-identical copy")
                checks.append({"condition": label, "scenario": scenario["scenario"], "pass": True})
            except (ValueError, KeyError, OSError) as exc:
                checks.append({"condition": label, "scenario": scenario["scenario"], "pass": False, "error": str(exc)})
    return checks


def run_control(case: str, intent: str, baseline_root: Path, output: Path) -> dict:
    workspace = baseline_root / "cases" / case / "public_workspace" / case
    ir_path = controls.BENCHMARK / "instances" / case / "gold/serviceflow.yaml"
    ir = controls.load(ir_path)
    matches = [b for b in ir["bindings"] if b["intent_id"] == intent]
    if len(matches) != 1:
        raise ValueError("Expected exactly one declared reference binding")
    scenarios = replay._fixture_scenarios(workspace)
    manifest = public_bindings.build(workspace, scenarios)
    controls.write_json(output / "public_execution_inputs.json", manifest)
    # Reuse the unchanged parser/sandbox machinery in a temporary in-process
    # context. No global changes persist after this invocation or affect v3.
    with patch.object(replay, "executor", executor), patch.object(replay, "install", install_v2):
        spec = replay.prepare_spec(ir, matches[0], workspace)
        input_checks = public_bindings.validate(spec, manifest)
        controls.write_json(output / "adapter_spec.json", spec)
        result = replay.invoke(spec, workspace, output / "execution")
    path_checks = check_paths(output / "execution")
    result.update(case=case, intent_id=intent, input_bindings=input_checks,
                  output_path_checks=path_checks, reference_control=True,
                  source_ir_sha256=controls.sha256(ir_path),
                  package_version=executor.EXECUTOR_VERSION, audit_protocol_version="4.0.0")
    result["control_pass"] = (result.get("state") == "executed" and result.get("output_schema_pass") is True
                              and result.get("input_probe", {}).get("pass") is True
                              and bool(path_checks) and all(c["pass"] for c in path_checks))
    return result


def fingerprint_inputs(baseline_root: Path, policy: dict) -> dict:
    hashes = controls.input_hashes()
    paths = set(IMPLEMENTATION + [baseline_root / "run.json", baseline_root / "input_sha256.json"])
    for case in policy["cases"]:
        workspace = baseline_root / "cases" / case / "public_workspace" / case
        paths.update(p for p in workspace.rglob("*") if p.is_file())
    hashes.update({str(p.resolve()): controls.sha256(p) for p in sorted(paths)})
    return hashes


def render(run: dict) -> str:
    lines = ["# V2 candidate reference controls", "",
             f"Package: {run['package_version']}; audit protocol: {run['audit_protocol_version']}.",
             f"State: {run['status']}; LLM calls: 0.", "",
             "Reference service controls only; not new G6-Assert or method scores.", "",
             "| Case | Invocation | State | Control pass |", "|---|---|---|---|"]
    for key, value in run["results"].items():
        case, intent = key.rsplit("/", 1)
        lines.append(f"| {case} | {intent} | {value.get('state')} | {value.get('control_pass', False)} |")
    passed = sum(v.get("control_pass") is True for v in run["results"].values())
    lines.extend(["", f"Passing controls: {passed}/{run['expected_controls']}.",
                  "Original public inputs/reference IR unchanged. Requested output locations are materialized in a separate intent/port namespace.",
                  "The v1 package, submitted results, prior audit runs, and DOI remain unchanged.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    policy = replay.read_json(CONFIG)
    baseline_root = ROOT / policy["control_directory"]
    baseline = replay.read_json(baseline_root / "run.json")
    if baseline["status"] != "complete" or not baseline["source_inputs_unchanged"]:
        raise ValueError("Reference baseline incomplete or changed")
    if controls.input_hashes() != replay.read_json(baseline_root / "input_sha256.json"):
        raise ValueError("Frozen v1 source inputs changed")
    if controls.environment() != baseline["environment"]:
        raise ValueError("Environment differs from reference baseline")
    roster = [(case, intent) for case, intents in policy["cases"].items() for intent in intents]
    if args.dry_run:
        print(json.dumps({"package_version": policy["package_version"],
                          "audit_protocol_version": policy["audit_protocol_version"],
                          "reference_controls": roster, "llm_calls": 0, "broad_model_replay": False}, indent=2))
        return 0
    hashes = fingerprint_inputs(baseline_root, policy)
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / "run.json")
        if (run["input_fingerprint"] != controls.fingerprint(hashes)
                or run["package_version"] != policy["package_version"]):
            raise ValueError("V2 inputs changed; preserve this run and start a new version")
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = ROOT / "audit/outputs" / f"package_v2_controls__{stamp}__{uuid.uuid4().hex[:8]}"
        output.mkdir(parents=True, exist_ok=False)
        run = {"package_version": policy["package_version"], "audit_protocol_version": policy["audit_protocol_version"],
               "expected_controls": len(roster), "llm_calls": 0, "results": {},
               "input_fingerprint": controls.fingerprint(hashes), "environment": controls.environment()}
        controls.write_json(output / "input_sha256.json", hashes)
        for path in IMPLEMENTATION:
            shutil.copy2(path, output / path.name)
    run["status"] = "running"
    controls.write_json(output / "run.json", run)
    print(f"Output: {output}", flush=True)
    verification = subprocess.run([sys.executable, "-m", "pytest", "-q", str(TESTS)], cwd=ROOT,
                                  capture_output=True, text=True, timeout=60)
    (output / "verification.txt").write_text(verification.stdout + verification.stderr)
    if verification.returncode:
        run["status"] = "verification_failed"
        controls.write_json(output / "run.json", run)
        raise ValueError("V2 verification failed; inspect verification.txt")
    for case, intent in roster:
        key = case + "/" + intent
        if key in run["results"]:
            continue
        target = output / "controls" / case / intent / ("attempt_" + uuid.uuid4().hex[:8])
        try:
            result = run_control(case, intent, baseline_root, target)
        except Exception as exc:
            result = {"state": "control_error", "control_pass": False,
                      "error": f"{type(exc).__name__}: {exc}"}
        result["artifact_directory"] = str(target)
        run["results"][key] = result
        controls.write_json(target / "control.json", result)
        controls.write_json(output / "run.json", run)
        (output / "summary.md").write_text(render(run))
        print(f"{key}: {result.get('state')} control_pass={result['control_pass']}", flush=True)
    run["source_inputs_unchanged"] = hashes == fingerprint_inputs(baseline_root, policy)
    passed = all(v.get("control_pass") for v in run["results"].values())
    run["status"] = ("inputs_changed" if not run["source_inputs_unchanged"] else
                     "complete" if passed else "complete_with_failures")
    controls.write_json(output / "run.json", run)
    (output / "summary.md").write_text(render(run))
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
