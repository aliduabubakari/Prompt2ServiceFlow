#!/usr/bin/env python3
"""Fixed-cohort v2 invocation replay: no new inference or composition repair."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_v2_reference_controls as v2

replay, controls, executor = v2.replay, v2.controls, v2.executor
CONFIG = ROOT / "audit/v2/model_replay.json"
TESTS = ROOT / "tests/unit/test_v2_model_replay.py"
IMPLEMENTATION = list(dict.fromkeys([Path(__file__).resolve(), CONFIG, TESTS,
                                    ROOT / "scripts/run_v2_reference_controls.py", *v2.IMPLEMENTATION]))


def verify_hashes(run_directory: Path, record: dict) -> dict:
    """Verify the stored hash manifest itself, then every listed source file."""
    hashes = replay.read_json(run_directory / "input_sha256.json")
    if controls.fingerprint(hashes) != record["input_fingerprint"]:
        raise ValueError("Recorded input hash manifest does not match its run fingerprint")
    for name, expected in hashes.items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        actual = controls.sha256(path) if path.is_file() else "MISSING"
        if actual != expected:
            raise ValueError(f"Immutable input changed: {name}")
    return hashes


def make_plan(inventory: dict) -> tuple[list, list]:
    """Select by declared adapter coverage ONLY, never by previous outcome."""
    targets, ledger, seen_sources, seen_targets = [], [], set(), set()
    for source in inventory["sources"]:
        if source["kind"] != "model":
            continue
        if source["id"] in seen_sources:
            raise ValueError("Duplicate inventory source identity")
        seen_sources.add(source["id"])
        prior = inventory["results"][source["id"]]
        selected, out_of_scope = [], 0
        for observation in prior.get("invocations", []):
            service, version = observation["service_id"], observation["service_version"]
            if service not in executor.REGISTRY or version != executor.REGISTRY[service]["version"]:
                out_of_scope += 1
                continue
            identity = (source["id"], observation["intent_id"], service, version)
            if identity in seen_targets:
                raise ValueError("Duplicate target invocation")
            seen_targets.add(identity)
            number = len(targets)
            target = {"id": f"target_{number:04d}", "source": source,
                      "intent_id": observation["intent_id"], "service_id": service,
                      "service_version": version, "prior_state": observation["state"],
                      "prior_reason": observation.get("reason"),
                      "prior_execution_errors": observation.get("execution_errors", [])}
            targets.append(target)
            selected.append(target["id"])
        ledger.append({"source": source, "prior_source_state": prior["state"],
                       "original_invocation_count": len(prior.get("invocations", [])),
                       "target_ids": selected, "out_of_scope_invocations": out_of_scope})
    return targets, ledger


def verify_mapping(output: Path, spec: dict, include_changed: bool) -> list[dict]:
    """Check complete port identity as well as the actual snapshot bytes."""
    expected = {o["port"]: o for o in spec["outputs"]}
    labels = ("base_execution", "changed_execution") if include_changed else ("base_execution",)
    checks = []
    for label in labels:
        directory = output / label
        try:
            index = replay.read_json(directory / "index.json")
            if not index:
                raise ValueError("Empty execution index")
            for scenario in index:
                snapshot = executor.inside(directory, scenario["directory"])
                mapping = replay.read_json(snapshot / "logs/public_output_bindings.json")
                if (mapping["contract_version"] != executor.CONTRACT_VERSION
                        or mapping["intent_id"] != spec["intent_id"]):
                    raise ValueError("Wrong output contract or intent")
                ports = [o["port"] for o in mapping["outputs"]]
                if len(ports) != len(set(ports)) or set(ports) != set(expected):
                    raise ValueError("Missing, duplicate, or unexpected output port mapping")
                for item in mapping["outputs"]:
                    bound = expected[item["port"]]
                    canonical = "artifacts/" + bound["artifact_id"] + bound["suffix"]
                    if item["artifact_id"] != bound["artifact_id"] or item["canonical_path"] != canonical:
                        raise ValueError("Output mapping changed a bound artifact identity")
                    if controls.sha256(executor.inside(snapshot, canonical)) != item["sha256"]:
                        raise ValueError("Bound output hash mismatch")
                    requested = item.get("materialized_path")
                    if requested:
                        if not requested.startswith("service_outputs/" + spec["intent_id"] + "/" + item["port"] + "/"):
                            raise ValueError("Requested output outside intent/port namespace")
                        if controls.sha256(executor.inside(snapshot, requested)) != item["sha256"]:
                            raise ValueError("Requested output is not byte-identical to its bound port")
                checks.append({"condition": label, "scenario": scenario["scenario"], "pass": True})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            checks.append({"condition": label, "pass": False, "error": str(exc)})
    return checks


def run_target(target: dict, baseline_root: Path, output: Path) -> dict:
    source = target["source"]
    path = Path(source["ir"])
    if not path.is_file():
        raise ValueError("Selected immutable final IR is no longer present")
    original_sha = controls.sha256(path)
    ir = controls.load(path)
    matches = [b for b in ir["bindings"] if b["intent_id"] == target["intent_id"]
               and b["service_id"] == target["service_id"] and b["service_version"] == target["service_version"]]
    if len(matches) != 1:
        raise ValueError("Selected invocation no longer matches its saved IR")
    workspace = baseline_root / "cases" / source["case"] / "public_workspace" / source["case"]
    result = {"source_ir_sha256": original_sha, "original_bindings_changed": False,
              "g6_assert": "not_measured", "workflow_correctness": "not_measured"}
    # Parser limitations remain separate from failures of actual computation.
    with patch.object(replay, "executor", executor), patch.object(replay, "install", v2.install_v2):
        try:
            spec = replay.prepare_spec(ir, matches[0], workspace)
        except executor.UnsupportedOperation as exc:
            return {**result, "state": "unsupported_operation", "reason": str(exc)}
        except (ValueError, KeyError, TypeError) as exc:
            return {**result, "state": "invalid_binding_or_input", "reason": str(exc)}
        scenarios = replay._fixture_scenarios(workspace)
        manifest = v2.public_bindings.build(workspace, scenarios)
        controls.write_json(output / "public_execution_inputs.json", manifest)
        try:
            input_checks = v2.public_bindings.validate(spec, manifest)
        except ValueError as exc:
            return {**result, "state": "blocked_public_input", "reason": str(exc)}
        controls.write_json(output / "adapter_spec.json", spec)
        invocation = replay.invoke(spec, workspace, output / "execution")
    result.update(invocation, input_bindings=input_checks)
    if result["state"] == "executed":
        checks = verify_mapping(output / "execution", spec,
                                result.get("input_probe", {}).get("state") == "completed")
        result["output_path_checks"] = checks
        result["output_path_pass"] = bool(checks) and all(c["pass"] for c in checks)
        if not result["output_path_pass"]:
            result["state"] = "output_path_rejected"
    if controls.sha256(path) != original_sha:
        raise ValueError("Saved IR changed during replay")
    return result


def render(run: dict, ledger: list) -> str:
    lines = ["# V2 targeted saved-invocation replay", "",
             f"Package: {run['package_version']}; audit protocol: {run['audit_protocol_version']}.",
             f"State: {run['status']}; recorded targets: {len(run['results'])}/{len(run['targets'])}; LLM calls: 0.", "",
             "Isolated invocations only. These are not G6-Assert scores or full-pipeline method comparisons.", "",
             "## Fixed original model-cell coverage", "",
             f"Original cells retained in coverage ledger: {len(ledger)}."]
    for state, count in sorted(Counter(x["prior_source_state"] for x in ledger).items()):
        lines.append(f"- Original {state}: {count}")
    lines += [f"- Out-of-scope service/version occurrences retained: {sum(x['out_of_scope_invocations'] for x in ledger)}.",
              "", "## Paired invocation outcomes", "",
              "| Model / method | Prior v3 state | V2 state | Count |", "|---|---|---|---:|"]
    counts, probes = Counter(), Counter()
    for target in run["targets"]:
        rec = run["results"].get(target["id"])
        if not rec:
            continue
        group = target["source"]["model"] + " / " + target["source"]["method"]
        counts[group, target["prior_state"], rec["state"]] += 1
        probe = rec.get("input_probe", {})
        if probe.get("state") == "completed":
            probes[group, "pass" if probe.get("pass") else "fail"] += 1
    lines.extend(f"| {g} | {old} | {new} | {n} |" for (g, old, new), n in sorted(counts.items()))
    lines += ["", "## Limited changed-input probes", "", "| Model / method | Outcome | Count |", "|---|---|---:|"]
    lines.extend(f"| {g} | {state} | {n} |" for (g, state), n in sorted(probes.items()))
    lines += ["", "Selection included prior failures and blocked invocations, not just successes.",
              "Missing/invalid IR and unsupported workflow services were retained in the original coverage ledger, not reclassified as executed.",
              "No saved bindings, prompts, fixtures, scenarios, assertions, submitted scores, or v1 artifacts were repaired or replaced.", ""]
    return "\n".join(lines)


def validate_preconditions(policy: dict):
    inventory_root, gate_root = ROOT / policy["inventory_run"], ROOT / policy["reference_gate"]
    inventory, gate = replay.read_json(inventory_root / "run.json"), replay.read_json(gate_root / "run.json")
    for record in (inventory, gate):
        if record["status"] != "complete" or not record.get("source_inputs_unchanged"):
            raise ValueError("Inventory/reference controls incomplete or changed")
        if record["environment"] != controls.environment():
            raise ValueError("Environment differs from completed controls")
    if gate["package_version"] != executor.EXECUTOR_VERSION or gate["package_version"] != policy["package_version"]:
        raise ValueError("V2 executor version differs from passing reference controls")
    reference_policy = replay.read_json(v2.CONFIG)
    expected = {case + "/" + intent for case, intents in reference_policy["cases"].items() for intent in intents}
    if set(gate["results"]) != expected or not all(r.get("control_pass") is True for r in gate["results"].values()):
        raise ValueError("All fixed v2 reference controls must pass before model replay")
    inventory_hashes = verify_hashes(inventory_root, inventory)
    gate_hashes = verify_hashes(gate_root, gate)
    baseline_root = Path(inventory["control_directory"])
    if controls.fingerprint(v2.fingerprint_inputs(baseline_root, reference_policy)) != gate["input_fingerprint"]:
        raise ValueError("Current v2 code differs from verified reference condition")
    return inventory, baseline_root, inventory_root, gate_root, {**inventory_hashes, **gate_hashes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    policy = replay.read_json(CONFIG)
    print("Checking immutable v3 inventory and passing v2 reference controls...", flush=True)
    inventory, baseline_root, inventory_root, gate_root, hashes = validate_preconditions(policy)
    targets, ledger = make_plan(inventory)
    if not targets:
        raise ValueError("Empty target roster")
    prior_counts = dict(Counter(t["prior_state"] for t in targets))
    if args.dry_run:
        print(json.dumps({"package_version": policy["package_version"], "audit_protocol_version": policy["audit_protocol_version"],
                          "targets": len(targets), "prior_target_states": prior_counts,
                          "original_model_cells_retained": len(ledger), "llm_calls": 0}, indent=2))
        return 0
    extra = list(dict.fromkeys([*IMPLEMENTATION, inventory_root / "run.json", inventory_root / "input_sha256.json",
                                gate_root / "run.json", gate_root / "input_sha256.json"]))
    hashes.update({str(p.resolve()): controls.sha256(p) for p in extra})
    fingerprint = controls.fingerprint(hashes)
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / "run.json")
        if run["input_fingerprint"] != fingerprint or run["targets"] != targets:
            raise ValueError("Replay implementation or immutable input roster changed; start a new run")
        if replay.read_json(output / "coverage_ledger.json") != ledger:
            raise ValueError("Original model-cell coverage ledger changed")
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = ROOT / "audit/outputs" / f"package_v2_model_replay__{stamp}__{uuid.uuid4().hex[:8]}"
        output.mkdir(parents=True, exist_ok=False)
        run = {"package_version": policy["package_version"], "audit_protocol_version": policy["audit_protocol_version"],
               "status": "running", "input_fingerprint": fingerprint, "environment": controls.environment(),
               "llm_calls": 0, "inventory_directory": str(inventory_root), "reference_gate": str(gate_root),
               "targets": targets, "results": {}}
        controls.write_json(output / "coverage_ledger.json", ledger)
        controls.write_json(output / "input_sha256.json", hashes)
        controls.write_json(output / "roster.json", targets)
        copies = output / "implementation"
        for path in IMPLEMENTATION:
            relative = path.relative_to(ROOT)
            (copies / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copies / relative)
    print(f"Output: {output}", flush=True)
    run["status"] = "running"
    controls.write_json(output / "run.json", run)
    verification = subprocess.run([sys.executable, "-m", "pytest", "-q", str(v2.TESTS), str(TESTS)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / "verification.txt").write_text(verification.stdout + verification.stderr)
    if verification.returncode:
        run["status"] = "verification_failed"
        controls.write_json(output / "run.json", run)
        raise ValueError("Replay verification failed; inspect verification.txt")
    for number, target in enumerate(targets):
        if target["id"] in run["results"]:
            continue
        destination = output / "targets" / target["id"] / ("attempt_" + uuid.uuid4().hex[:8])
        try:
            result = run_target(target, baseline_root, destination)
        except Exception as exc:
            result = {"state": "runner_error", "error": f"{type(exc).__name__}: {exc}"}
        result["artifact_directory"] = str(destination)
        controls.write_json(destination / "result.json", result)
        run["results"][target["id"]] = result
        controls.write_json(output / "run.json", run)
        (output / "summary.md").write_text(render(run, ledger))
        print(f"[{number+1}/{len(targets)}] {target['source']['id']} / {target['intent_id']}: {target['prior_state']} -> {result['state']}", flush=True)
    try:
        verify_hashes(output, run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run["integrity_error"] = str(exc)
    run["source_inputs_unchanged"] = unchanged
    run["status"] = ("inputs_changed" if not unchanged else "complete_with_errors" if any(
        r["state"] == "runner_error" for r in run["results"].values()) else "complete")
    controls.write_json(output / "run.json", run)
    (output / "summary.md").write_text(render(run, ledger))
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
