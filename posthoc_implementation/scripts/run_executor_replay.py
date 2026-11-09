#!/usr/bin/env python3
"""Replay a declared subset of service invocations without LLM inference.

Read-only saved compositions and reference IR are inventoried separately.
Only explicit external inputs are consumed; unsupported upstream operations
are never replaced by reference outputs or schema-derived mock data. This
stage measures service-level executability/input dependence, NOT G6-Assert.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "audit"))
import run_reference_runtime_controls as controls
import service_executor_v3 as executor
import retention_adapter as retention
from prompt2serviceflow.experiments.runtime_compiler import _fixture_scenarios
from jsonschema import Draft202012Validator, FormatChecker

CONFIG = ROOT / "audit/config/executor_replay.v3.json"
IMPLEMENTATION = [Path(__file__).resolve(), ROOT / "audit/service_executor_v3.py",
                  ROOT / "audit/retention_adapter.py", CONFIG,
                  ROOT / "tests/unit/test_executor_replay.py"]


def read_json(path):
    return json.loads(Path(path).read_text())


def selected_ir(run_root: Path, method: str) -> Path:
    # Exact final-submission locations; never glob intermediate repair attempts
    # or choose whichever artifact happens to score best.
    if method == "m5":
        return run_root / "agent_workspace/submission/serviceflow.yaml"
    return run_root / "submission/serviceflow.yaml"


def collect_sources(policy: dict, baseline: dict, batches: list[Path]) -> list[dict]:
    result = []
    for case in baseline["results"]:
        path = controls.BENCHMARK / "instances" / case / "gold/serviceflow.yaml"
        result.append({"id": "reference/" + case, "case": case, "kind": "reference",
                       "method": "reference", "model": "reference", "ir": str(path)})
    identities = set()
    for batch in batches:
        document = read_json(batch)
        for observation in document["runs"]:
            method = observation["method"]
            if method not in policy["methods"]:
                continue
            case = observation["split"] + "/" + observation["instance"]
            if case not in baseline["results"]:
                raise ValueError("Saved cell not covered by reference control baseline")
            key = (observation["model"], method, case, observation["sample_index"])
            if key in identities:
                raise ValueError(f"Duplicate immutable cell identity: {key}")
            identities.add(key)
            manifest = Path(observation["manifest_path"]).resolve()
            # Do not follow arbitrary paths out of the declared run archive.
            if not manifest.is_relative_to(batch.parent.resolve()):
                raise ValueError("Saved manifest escapes its batch directory")
            metadata = read_json(manifest)
            identity = metadata.get("instance", {})
            if (metadata.get("model", {}).get("model_id") != key[0]
                    or metadata.get("method", {}).get("id") != method
                    or identity.get("split") != observation["split"]
                    or identity.get("id") != observation["instance"]
                    or metadata.get("sample_index") != key[-1]):
                raise ValueError("Saved manifest and batch cell identities disagree")
            result.append({"id": "/".join(map(str, key)), "case": case, "kind": "model",
                           "model": key[0], "method": method, "sample_index": key[-1],
                           "original_observation_status": observation.get("status"),
                           "original_method_status": metadata.get("method_status", metadata.get("driver_status")),
                           "batch": str(batch), "manifest": str(manifest),
                           "ir": str(selected_ir(manifest.parent, method))})
    return result


def prepare_spec(ir: dict, binding: dict, workspace: Path) -> dict:
    service = binding["service_id"]
    definition = executor.REGISTRY[service]
    artifacts = {a["artifact_id"]: a for a in ir["artifacts"]}
    if len(artifacts) != len(ir["artifacts"]):
        raise ValueError("Duplicate artifact declarations")
    ins, outs = {}, []
    for item in binding.get("input_bindings", []):
        port = item["port"]
        if port in ins:
            raise ValueError("Duplicate input port")
        if port not in definition["inputs"] | definition["optional_inputs"]:
            raise ValueError("Unknown service input port")
        artifact = artifacts[item["artifact_id"]]
        if artifact.get("producer") is not None:
            raise executor.UnsupportedOperation("upstream_result_required")
        if not artifact.get("fixture_ref"):
            raise executor.UnsupportedOperation("external_fixture_binding_missing")
        relative = retention.fixture_relative(artifact["fixture_ref"])
        ins[port] = {"relative": relative.as_posix(), "fixture_ref": artifact["fixture_ref"],
                     "suffix": executor.artifact_suffix(artifact)}
    if not definition["inputs"].issubset(ins):
        raise ValueError("Required input ports are not bound")
    for item in binding.get("output_bindings", []):
        if item["port"] not in definition["outputs"]:
            raise ValueError("Unknown service output port")
        artifact = artifacts[item["artifact_id"]]
        if artifact.get("producer") != binding["intent_id"]:
            raise ValueError("Bound output producer differs from its service intent")
        schema = None
        if artifact.get("schema_ref"):
            schema = controls.load(executor.inside(workspace, artifact["schema_ref"]))
            def has_reference(node):
                if isinstance(node, dict):
                    return "$ref" in node or any(has_reference(v) for v in node.values())
                return isinstance(node, list) and any(has_reference(v) for v in node)
            if has_reference(schema):
                raise executor.UnsupportedOperation("Referenced output schemas require a reviewed local resolver")
        outs.append({"port": item["port"], "artifact_id": executor.identifier(item["artifact_id"]),
                     "suffix": executor.artifact_suffix(artifact), "schema": schema})
    ports = [item["port"] for item in outs]
    if len(ports) != len(set(ports)) or set(ports) != definition["outputs"]:
        raise ValueError("Required outputs missing or output ports duplicated")
    if len({o['artifact_id'] for o in outs}) != len(outs):
        raise ValueError("Output artifacts collide")
    if binding.get("secret_bindings"):
        raise executor.UnsupportedOperation("Secret-dependent invocation not supported")
    unknown = set(binding.get("parameter_bindings", {})) - definition["parameters"]
    if unknown:
        raise executor.UnsupportedOperation("unimplemented_parameters:" + ",".join(sorted(unknown)))
    if service == "retention_cutoff_config_resolver" and not binding.get("parameter_bindings", {}).get("reference_time"):
        raise executor.UnsupportedOperation("Explicit logical reference_time is required for deterministic replay")
    return {"service_id": service, "service_version": binding["service_version"],
            "intent_id": binding["intent_id"], "inputs": ins, "outputs": outs,
            "parameters": binding.get("parameter_bindings", {})}


def install(spec: dict, destination: Path, fixtures: Path, scenarios: list) -> dict:
    runtime = destination / "runtime/scripts"
    runtime.mkdir(parents=True)
    for source in (ROOT / "audit/service_executor_v3.py", ROOT / "audit/retention_adapter.py"):
        shutil.copy2(source, runtime / source.name)
    controls.write_json(runtime / "spec.json", spec)
    # Only our reviewed wrapper executes. Saved model scripts are never copied.
    (runtime / "invoke.py").write_text(
        'import argparse,json\nfrom pathlib import Path\nfrom service_executor_v3 import run,UnsupportedOperation\n'
        'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path)\n'
        'a=p.parse_args()\n'
        'try:\n run(json.loads(Path(__file__).with_name("spec.json").read_text()),a.workspace,a.fixtures)\n'
        'except UnsupportedOperation as e:\n print("UNSUPPORTED_OPERATION:",e);raise SystemExit(3)\n'
        'except (ValueError,KeyError,OSError,TypeError) as e:\n print("INVOCATION_REJECTED:",e);raise SystemExit(2)\n')
    shutil.copytree(fixtures, destination / "fixtures")
    manifest = {"runtime_manifest_version": "0.1.0", "pipeline_id": "isolated_service_replay",
                "image": "python:3.12-slim", "workflow_parameters": [],
                "tasks": [{"intent_id": executor.identifier(spec["intent_id"]),
                           "script": "scripts/invoke.py",
                           "arguments": ["--workspace", "{workspace}", "--fixtures", "{fixtures}"],
                           "retries": 0}], "scenarios": scenarios}
    (destination / "runtime/manifest.yaml").write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def validate_outputs(results: list, spec: dict) -> list:
    checks = []
    for result in results:
        for output in spec["outputs"]:
            key = "artifacts/" + output["artifact_id"] + output["suffix"]
            raw = result["_snapshot"].get(key)
            error = None
            if raw is None:
                error = "Output absent"
            elif output["suffix"] == ".json":
                try:
                    data = json.loads(raw)
                    if output.get("schema"):
                        Draft202012Validator(output["schema"], format_checker=FormatChecker()).validate(data)
                except Exception as exc:
                    error = str(exc)
            checks.append({"scenario": result["scenario"], "port": output["port"],
                           "pass": error is None, "error": error})
    return checks


def perturb(spec: dict, destination: Path, manifest: dict) -> list:
    """Change actual active inputs. Expected relations come from service operations,
    not hidden assertions: one additional row or seven more retention days.
    """
    service = spec["service_id"]
    port = next(iter(executor.REGISTRY[service]["inputs"]))
    bound = spec["inputs"][port]
    changed, seen = [], {}
    for scenario in manifest["scenarios"]:
        root = executor.inside(destination, scenario["fixture_root"])
        path = executor.inside(root, bound["relative"])
        if str(path) in seen:
            changed.append({"scenario": scenario["name"], **seen[str(path)]})
            continue
        if service == "retention_cutoff_config_resolver":
            data = read_json(path)
            name = spec["parameters"]["max_age_parameter_name"]
            if name not in data or isinstance(data[name], bool) or not isinstance(data[name], int):
                raise executor.UnsupportedOperation("Changed-input retention probe requires explicit integer age")
            before, after = data[name], data[name] + 7
            data[name] = after
            controls.write_json(path, data)
        elif service == "csv_tabular_schema_validating_loader":
            with path.open(newline="") as handle:
                table = list(csv.reader(handle, delimiter=executor.delimiter(spec["parameters"])))
            if len(table) < 2:
                raise executor.UnsupportedOperation("Changed-input CSV probe requires a data row")
            populated = [row for row in table[1:] if row]
            if not populated:
                raise executor.UnsupportedOperation("Changed-input CSV probe requires a data row")
            before, after = len(populated), len(populated) + 1
            with path.open("w", newline="") as handle:
                writer = csv.writer(handle, delimiter=executor.delimiter(spec["parameters"]))
                writer.writerows(table + [populated[-1]])
        else:
            data = read_json(path)
            if not data.get("rows"):
                raise executor.UnsupportedOperation("Changed-input export probe requires a row")
            before, after = len(data["rows"]), len(data["rows"]) + 1
            data["rows"].append(copy.deepcopy(data["rows"][-1]))
            controls.write_json(path, data)
        record = {"original": before, "changed": after, "input_relative": bound["relative"]}
        seen[str(path)] = record
        changed.append({"scenario": scenario["name"], **record})
    return changed


def observe_measure(result: dict, spec: dict):
    port, field = {
        "retention_cutoff_config_resolver": ("retention_config", "max_age_days"),
        "csv_tabular_schema_validating_loader": ("validated_dataset", "row_count"),
        "structured_json_to_csv_exporter": ("export_status", "rows_written")}[spec["service_id"]]
    output = next(o for o in spec["outputs"] if o["port"] == port)
    data = result["_snapshot"].get("artifacts/" + output["artifact_id"] + ".json")
    return json.loads(data).get(field) if data else None


def invoke(spec: dict, workspace: Path, output: Path) -> dict:
    scenarios = _fixture_scenarios(workspace)
    for scenario in scenarios:
        root = executor.inside(workspace, scenario["fixture_root"])
        for bound in spec["inputs"].values():
            if not executor.inside(root, bound["relative"]).is_file():
                return {"state": "blocked_public_input", "reason": "Bound input absent from active public scenario",
                        "scenario": scenario["name"], "fixture_ref": bound["fixture_ref"]}
    manifest = install(spec, output / "base", workspace / "fixtures", scenarios)
    results = controls._execute_scenarios(output / "base", manifest, sandbox_generated=True)
    snapshots = controls.persist_snapshots(results, output / "base_execution")
    errors = [e for item in results for e in item["_errors"]]
    if errors:
        state = "unsupported_operation" if any("UNSUPPORTED_OPERATION:" in e for e in errors) else "execution_error"
        return {"state": state, "execution_errors": errors, "execution": snapshots}
    checks = validate_outputs(results, spec)
    record = {"state": "executed", "execution": snapshots, "schema_checks": checks,
              "output_schema_pass": bool(checks) and all(item["pass"] for item in checks),
              "g6_assert": "not_measured", "workflow_correctness": "not_measured",
              "original_hidden_assertions_used": False}
    if not record["output_schema_pass"]:
        record["state"] = "output_schema_rejected"
        return record
    changed_root = output / "changed"
    changed_manifest = install(spec, changed_root, workspace / "fixtures", scenarios)
    try:
        changes = perturb(spec, changed_root, changed_manifest)
    except executor.UnsupportedOperation as exc:
        record["input_probe"] = {"state": "not_applicable", "reason": str(exc)}
        return record
    altered = controls._execute_scenarios(changed_root, changed_manifest, sandbox_generated=True)
    record["changed_execution"] = controls.persist_snapshots(altered, output / "changed_execution")
    changed_checks = validate_outputs(altered, spec)
    observations = []
    by_name = {r["scenario"]: r for r in results}
    expected = {r["scenario"]: r for r in changes}
    for item in altered:
        relation = expected[item["scenario"]]
        before = observe_measure(by_name[item["scenario"]], spec)
        after = observe_measure(item, spec)
        observations.append({"scenario": item["scenario"], "input": relation,
                             "original_output": before, "changed_output": after,
                             "pass": before == relation["original"] and after == relation["changed"]
                                     and not item["_errors"]})
    record["input_probe"] = {"state": "completed", "observations": observations,
                             "schema_checks": changed_checks,
                             "pass": bool(observations) and all(r["pass"] for r in observations)
                                     and all(c["pass"] for c in changed_checks)}
    return record


def replay(source: dict, workspace: Path, output: Path) -> dict:
    path = Path(source["ir"])
    if not path.is_file():
        return {"state": "missing_saved_ir", "invocations": []}
    try:
        ir = controls.load(path)
        if not isinstance(ir, dict) or not isinstance(ir.get("bindings"), list):
            raise ValueError("IR has no binding list")
        intent_ids = [i['intent_id'] for i in ir['service_intents']]
        binding_ids = [b['intent_id'] for b in ir['bindings']]
        if (len(intent_ids) != len(set(intent_ids)) or len(binding_ids) != len(set(binding_ids))
                or any(i not in intent_ids for i in binding_ids)):
            raise ValueError("Duplicate or orphan service bindings")
        for binding in ir['bindings']:
            if not isinstance(binding['service_id'], str) or not isinstance(binding['service_version'], str):
                raise ValueError("Service identity/version must be strings")
    except Exception as exc:
        return {"state": "invalid_saved_ir", "error": f"{type(exc).__name__}: {exc}", "invocations": []}
    try:
        records = []
        for number, binding in enumerate(ir["bindings"]):
            service = binding["service_id"]
            record = {"intent_id": binding["intent_id"], "service_id": service,
                      "service_version": binding["service_version"]}
            if service not in executor.REGISTRY or binding["service_version"] != executor.REGISTRY[service]["version"]:
                record.update(state="unsupported_service", reason="No adapter for exact service/version")
            else:
                try:
                    spec = prepare_spec(ir, binding, workspace)
                    destination = output / f"invocation_{number:03d}"
                    controls.write_json(destination / "spec.json", spec)
                    record.update(invoke(spec, workspace, destination))
                except executor.UnsupportedOperation as exc:
                    record.update(state="unsupported_operation", reason=str(exc))
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    record.update(state="invalid_binding_or_input", reason=str(exc))
                except Exception as exc:
                    record.update(state="runner_error", reason=f"{type(exc).__name__}: {exc}")
            records.append(record)
        return {"state": "inventoried", "invocations": records,
                "whole_pipeline_semantics": "not_measured", "branch_execution": "not_measured"}
    except Exception as exc:
        return {"state": "runner_error", "error": f"{type(exc).__name__}: {exc}", "invocations": []}


def render(run: dict) -> str:
    lines = ["# Service executor replay v3", "", "Isolated service invocations, not new method or G6-Assert scores.", "",
             f"State: {run['status']}; LLM calls: 0; records: {len(run['results'])}/{len(run['sources'])}.", "",
             "| Source | Invocation state | Count |", "|---|---|---:|"]
    totals = Counter()
    probes = Counter()
    backlog = Counter()
    limitations = Counter()
    source_totals = Counter()
    for source in run["sources"]:
        result = run["results"].get(source["id"], {})
        group = "reference" if source["kind"] == "reference" else source["model"] + " / " + source["method"]
        if result:
            source_totals[group, result["state"]] += 1
        if result.get("state") not in (None, "inventoried"):
            totals[group, result["state"]] += 1
        for item in result.get("invocations", []):
            totals[group, item["state"]] += 1
            if item["state"] == "unsupported_service":
                backlog[source["kind"], item["service_id"], item["service_version"]] += 1
            elif item["state"] in ("unsupported_operation", "blocked_public_input", "invalid_binding_or_input"):
                limitations[item["state"], item.get("reason", "unspecified")] += 1
            probe = item.get("input_probe", {})
            if probe.get("state") == "completed":
                probes[group, "pass" if probe["pass"] else "fail"] += 1
    lines.extend(f"| {group} | {state} | {count} |" for (group, state), count in sorted(totals.items()))
    lines.extend(["", "## Changed-input checks", "", "| Source | Outcome | Count |", "|---|---|---:|"])
    lines.extend(f"| {group} | {state} | {count} |" for (group, state), count in sorted(probes.items()))
    lines.extend(["", "## Saved composition coverage", "", "| Source | Composition state | Count |", "|---|---|---:|"])
    lines.extend(f"| {group} | {state} | {count} |" for (group, state), count in sorted(source_totals.items()))
    lines.extend(["", "## Most frequent unsupported services", "", "Counts are invocation occurrences, not unique pipelines.", "",
                  "| Source kind | Service | Version | Count |", "|---|---|---|---:|"])
    lines.extend(f"| {kind} | {service} | {version} | {count} |"
                 for (kind, service, version), count in backlog.most_common(20))
    lines.extend(["", "## Other replay limitations", ""])
    lines.extend(f"- {state}: {reason} ({count})" for (state, reason), count in limitations.most_common(20))
    lines.extend(["", "Unsupported, missing, invalid, and rejected invocations are retained, not excluded silently.",
                  "A service invocation running and consuming its input does not prove that the model selected the right service, input, or parameters.",
                  "No original assertions, restored fixtures, reference scenarios, or mock upstream outputs were used.", ""])
    return "\n".join(lines)


def hashes_for(sources, baseline_root, batches):
    hashes = controls.input_hashes()
    paths = set(IMPLEMENTATION + batches + [baseline_root / "run.json", baseline_root / "input_sha256.json"])
    for source in sources:
        paths.add(Path(source["ir"]))
        if source.get("manifest"):
            paths.add(Path(source["manifest"]))
    for case in {s["case"] for s in sources}:
        workspace = baseline_root / "cases" / case / "public_workspace" / case
        paths.update(p for p in workspace.rglob("*") if p.is_file())
    for path in paths:
        hashes[str(path.resolve())] = controls.sha256(path) if path.is_file() else "MISSING"
    return hashes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-summary", action="append", type=Path,
                        help="Override the three default model batches; repeat for multiple batches")
    parser.add_argument("--instances", nargs="+", help="Optional explicit split/instance selection")
    parser.add_argument("--control-run", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    policy = read_json(CONFIG)
    previous = None
    if args.resume:
        if args.batch_summary or args.instances or args.control_run:
            parser.error("Resume restores immutable selection; do not add selection options")
        previous = read_json(args.resume / "run.json")
        batches = [Path(p) for p in previous["batches"]]
        baseline_root = Path(previous["control_directory"])
    else:
        batches = [p.resolve() for p in args.batch_summary] if args.batch_summary else [Path(p) for p in policy["batches"]]
        baseline_root = (args.control_run or ROOT / policy["control_directory"]).resolve()
    baseline = read_json(baseline_root / "run.json")
    if baseline["status"] != "complete" or not baseline["source_inputs_unchanged"]:
        raise ValueError("Reference controls are incomplete or their inputs changed")
    if controls.input_hashes() != read_json(baseline_root / "input_sha256.json"):
        raise ValueError("Frozen baseline inputs changed")
    if controls.environment() != baseline["environment"]:
        raise ValueError("Environment differs from reference controls")
    if policy["services"] != {k: v["version"] for k, v in executor.REGISTRY.items()}:
        raise ValueError("Registry and frozen service roster differ")
    sources = collect_sources(policy, baseline, batches)
    selection = previous.get("selection") if previous else args.instances
    if selection:
        allowed = {c['split'] + '/' + c['instance'] for c in controls.choose_cases({}, selection, False)}
        if not allowed.issubset(baseline["results"]):
            raise ValueError("Unknown selected case")
        sources = [s for s in sources if s["case"] in allowed]
    if previous and sources != previous["sources"]:
        raise ValueError("Saved source inventory changed")
    if args.dry_run:
        print(json.dumps({"protocol": policy["protocol_version"], "sources": len(sources),
                          "by_group": dict(Counter(s['model'] + '/' + s['method'] for s in sources)),
                          "missing_saved_ir": sum(not Path(s['ir']).is_file() for s in sources),
                          "services": policy["services"], "llm_calls": 0,
                          "scope": policy["unit_of_analysis"]}, indent=2))
        return 0
    hashes = hashes_for(sources, baseline_root, batches)
    if previous:
        if previous["input_fingerprint"] != controls.fingerprint(hashes):
            raise ValueError("Replay inputs or implementation changed; start a fresh versioned run")
        output, run = args.resume.resolve(), previous
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = ROOT / "audit/outputs" / f"executor_replay_v3__{stamp}__{uuid.uuid4().hex[:8]}"
        output.mkdir(parents=True, exist_ok=False)
        run = {"protocol_version": policy["protocol_version"], "sources": sources, "selection": selection,
               "control_directory": str(baseline_root), "batches": list(map(str, batches)),
               "input_fingerprint": controls.fingerprint(hashes), "environment": controls.environment(),
               "llm_calls": 0, "results": {}}
        controls.write_json(output / "input_sha256.json", hashes)
        for path in IMPLEMENTATION:
            shutil.copy2(path, output / path.name)
    print(f"Output: {output}", flush=True)
    run["status"] = "running"
    controls.write_json(output / "run.json", run)
    # Verification is a gate, not a record of improved benchmark performance.
    verification = subprocess.run([sys.executable, "-m", "pytest", "-q", str(IMPLEMENTATION[-1])],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / "verification.txt").write_text(verification.stdout + verification.stderr)
    if verification.returncode:
        run["status"] = "verification_failed"
        controls.write_json(output / "run.json", run)
        raise ValueError("Executor unit/negative controls failed; see verification.txt")
    for number, source in enumerate(sources):
        if source["id"] in run["results"]:
            continue
        folder = output / "records" / f"{number:05d}" / ("attempt_" + uuid.uuid4().hex[:8])
        workspace = baseline_root / "cases" / source["case"] / "public_workspace" / source["case"]
        if not (workspace / "workspace.yaml").is_file():
            raise ValueError("Missing reference public workspace")
        result = replay(source, workspace, folder)
        result["artifact_directory"] = str(folder)
        controls.write_json(folder / "record.json", result)
        run["results"][source["id"]] = result
        controls.write_json(output / "run.json", run)
        (output / "summary.md").write_text(render(run))
        print(f"[{number+1}/{len(sources)}] {source['id']}: {dict(Counter(r['state'] for r in result.get('invocations', []))) or result['state']}", flush=True)
    unchanged = hashes_for(sources, baseline_root, batches) == hashes
    run["source_inputs_unchanged"] = unchanged
    runner_errors = any(r.get("state") == "runner_error" or any(
        item.get("state") == "runner_error" for item in r.get("invocations", []))
        for r in run["results"].values())
    run["status"] = ("inputs_changed" if not unchanged else
                     "complete_with_errors" if runner_errors else "complete")
    controls.write_json(output / "run.json", run)
    (output / "summary.md").write_text(render(run))
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
