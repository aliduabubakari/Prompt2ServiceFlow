"""G0-G6 validation and local mock execution for a benchmark instance."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from prompt2serviceflow.compiler.argo import build_resources, load_runtime_manifest
from prompt2serviceflow.validators.schema_validation import (
    load_document,
    load_schema,
    validate_against_schema,
    validate_serviceflow_references,
)


ROOT = Path(__file__).resolve().parents[3]
CONFIGMAP_DATA_LIMIT_BYTES = 1_048_576
GENERATED_TASK_TIMEOUT_SECONDS = 60
GENERATED_TASK_MEMORY = "512m"
GENERATED_TASK_CPUS = "1.0"
GENERATED_TASK_PIDS = 64
DISTRACTOR_LABELS = {
    "gold",
    "semantic_mismatch",
    "format_mismatch",
    "target_mismatch",
    "deprecated_or_incompatible",
    "policy_incompatible",
    "missing_required_output",
    "generic_escape_hatch",
    "contract_mismatch",
}


def _configmap_data_size_bytes(resource: dict[str, Any]) -> int:
    """Return the payload size for a ConfigMap's text and binary entries."""

    data = resource.get("data") if isinstance(resource.get("data"), dict) else {}
    binary_data = resource.get("binaryData") if isinstance(resource.get("binaryData"), dict) else {}
    text_size = sum(
        len(str(key).encode("utf-8")) + len(str(value).encode("utf-8"))
        for key, value in data.items()
    )
    binary_size = sum(
        len(str(key).encode("utf-8")) + len(base64.b64decode(str(value)))
        for key, value in binary_data.items()
    )
    return text_size + binary_size


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _catalog_index(catalog_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for path in sorted((catalog_dir / "services").glob("*.yaml")):
        descriptor = load_document(path)
        result[(descriptor["service_id"], descriptor["version"])] = descriptor
    return result


def _manifest_row(source: dict[str, Any]) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matches = [row for row in rows if row["description_path"] == source["description_path"]]
    if len(matches) != 1:
        raise ValueError(
            f"expected one manifest row for {source['description_path']!r}, found {len(matches)}"
        )
    return matches[0]


def _validate_candidate_grounding(
    serviceflow: dict[str, Any],
    candidates: dict[str, Any],
    labels: dict[str, Any],
    catalog: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for binding in serviceflow["bindings"]:
        key = (binding["service_id"], binding["service_version"])
        descriptor = catalog.get(key)
        if not descriptor:
            errors.append(f"unresolved service {key[0]}:{key[1]}")
        elif descriptor["lifecycle"]["status"] != "active":
            errors.append(f"service {key[0]} is not active")

    candidate_items = candidates["candidate_sets"]
    label_items = labels["candidate_sets"]
    candidate_ids = [item["candidate_set_id"] for item in candidate_items]
    label_ids = [item["candidate_set_id"] for item in label_items]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("public candidate-set IDs are not unique")
    if len(label_ids) != len(set(label_ids)):
        errors.append("private candidate-set IDs are not unique")
    candidate_sets = {item["candidate_set_id"]: item for item in candidate_items}
    label_sets = {item["candidate_set_id"]: item for item in label_items}
    if set(candidate_sets) != set(label_sets):
        errors.append("public candidate sets and private label sets do not align")

    intents = {item["intent_id"]: item for item in serviceflow["service_intents"]}
    expected_refs: dict[str, list[str]] = {}
    for binding in serviceflow["bindings"]:
        refs = expected_refs.setdefault(binding["service_id"], [])
        for ref in intents[binding["intent_id"]]["source_step_refs"]:
            if ref not in refs:
                refs.append(ref)

    required_services = [item["required_service_id"] for item in label_items]
    if len(required_services) != len(set(required_services)):
        errors.append("each bound service must have exactly one candidate set")
    if set(required_services) != set(expected_refs):
        missing = sorted(set(expected_refs) - set(required_services))
        extra = sorted(set(required_services) - set(expected_refs))
        if missing:
            errors.append(f"bound services without gold candidate sets: {missing}")
        if extra:
            errors.append(f"candidate sets for unbound services: {extra}")

    for candidate_set_id, candidate_set in candidate_sets.items():
        label_set = label_sets.get(candidate_set_id)
        if not label_set:
            continue
        service_ids = candidate_set["service_ids"]
        service_id_set = set(service_ids)
        if not 3 <= len(service_ids) <= 6:
            errors.append(f"{candidate_set_id}: candidate count must be between 3 and 6")
        if len(service_ids) != len(service_id_set):
            errors.append(f"{candidate_set_id}: candidate service IDs are not unique")
        if service_id_set != set(label_set["labels"]):
            errors.append(f"{candidate_set_id}: candidate IDs and labels do not align")

        required_service_id = label_set["required_service_id"]
        gold_services = [
            service_id for service_id, label in label_set["labels"].items() if label == "gold"
        ]
        if gold_services != [required_service_id]:
            errors.append(f"{candidate_set_id}: must contain exactly one correct gold relation")
        unknown_labels = sorted(set(label_set["labels"].values()) - DISTRACTOR_LABELS)
        if unknown_labels:
            errors.append(f"{candidate_set_id}: unknown candidate labels {unknown_labels}")

        expected = expected_refs.get(required_service_id)
        received = candidate_set["source_step_refs"]
        if len(received) != len(set(received)):
            errors.append(f"{candidate_set_id}: source-step refs are not unique")
        if expected is not None and set(received) != set(expected):
            errors.append(
                f"{candidate_set_id}: source-step coverage does not match intents "
                f"bound to {required_service_id}"
            )
        for service_id in service_ids:
            if not any(key[0] == service_id for key in catalog):
                errors.append(f"{candidate_set_id}: unknown candidate service {service_id}")
    return errors


def _json_path(document: Any, path: str) -> Any:
    current = document
    parts = re.split(r"\.(?![^\[]*\])", path)
    for part in parts:
        match = re.fullmatch(r"([^\[]+)(?:\[(.+)\])?", part)
        if match is None:
            raise KeyError(f"unsupported JSON path segment {part!r}")
        key, selector = match.groups()
        current = current[int(key)] if isinstance(current, list) else current[key]
        if selector is None:
            continue
        if selector.isdigit():
            current = current[int(selector)]
            continue
        filter_match = re.fullmatch(
            r"\?\(@\.([A-Za-z_][A-Za-z0-9_]*)\s*==\s*(['\"])(.*?)\2\)",
            selector,
        )
        if filter_match and isinstance(current, list):
            field, _, expected = filter_match.groups()
            current = [
                item
                for item in current
                if isinstance(item, dict) and str(item.get(field)) == expected
            ]
            continue
        raise KeyError(f"unsupported JSON path selector [{selector}]")
    return current


def _run_gate(name: str, check: Callable[[], list[str]], description: str) -> dict[str, Any]:
    try:
        errors = check()
    except Exception as exc:  # Report validation failures uniformly.
        errors = [str(exc)]
    return {
        "gate": name,
        "status": "pass" if not errors else "fail",
        "checks": [description],
        "errors": errors,
    }


def _validate_contract_closure(
    serviceflow: dict[str, Any], catalog: dict[tuple[str, str], dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    artifacts = {item["artifact_id"]: item for item in serviceflow["artifacts"]}
    intents = {item["intent_id"]: item for item in serviceflow["service_intents"]}
    for binding in serviceflow["bindings"]:
        key = (binding["service_id"], binding["service_version"])
        descriptor = catalog.get(key)
        if not descriptor:
            continue
        interface = descriptor["interface"]
        input_ports = {item["name"]: item for item in interface["inputs"]}
        output_ports = {item["name"]: item for item in interface["outputs"]}
        parameters = {item["name"]: item for item in interface["parameters"]}
        secrets = {item["name"]: item for item in interface["secrets"]}
        mapped_inputs: dict[str, list[str]] = defaultdict(list)
        mapped_outputs: dict[str, list[str]] = defaultdict(list)
        for item in binding["input_bindings"]:
            mapped_inputs[item["port"]].append(item["artifact_id"])
        for item in binding["output_bindings"]:
            mapped_outputs[item["port"]].append(item["artifact_id"])
        mapped_secrets = {item["secret"] for item in binding["secret_bindings"]}
        intent_id = binding["intent_id"]

        for port, artifact_ids in mapped_inputs.items():
            if port not in input_ports:
                errors.append(f"{intent_id}: unknown input port {port!r}")
                continue
            if input_ports[port]["cardinality"] != "many" and len(artifact_ids) != 1:
                errors.append(
                    f"{intent_id}: input port {port!r} does not accept multiple artifacts"
                )
            for artifact_id in artifact_ids:
                if artifacts[artifact_id]["data_type"] != input_ports[port]["data_type"]:
                    errors.append(
                        f"{intent_id}: input {port!r} expects {input_ports[port]['data_type']}, "
                        f"got {artifacts[artifact_id]['data_type']}"
                    )
        for port, artifact_ids in mapped_outputs.items():
            if port not in output_ports:
                errors.append(f"{intent_id}: unknown output port {port!r}")
                continue
            if output_ports[port]["cardinality"] != "many" and len(artifact_ids) != 1:
                errors.append(
                    f"{intent_id}: output port {port!r} does not accept multiple artifacts"
                )
            for artifact_id in artifact_ids:
                if artifacts[artifact_id]["data_type"] != output_ports[port]["data_type"]:
                    errors.append(
                        f"{intent_id}: output {port!r} expects {output_ports[port]['data_type']}, "
                        f"got {artifacts[artifact_id]['data_type']}"
                    )
        for port, spec in input_ports.items():
            if spec["required"] and port not in mapped_inputs:
                errors.append(f"{intent_id}: required input port {port!r} is not bound")
        for port, spec in output_ports.items():
            if spec["required"] and port not in mapped_outputs:
                errors.append(f"{intent_id}: required output port {port!r} is not bound")
        for parameter, spec in parameters.items():
            if spec["required"] and parameter not in binding["parameter_bindings"]:
                errors.append(f"{intent_id}: required parameter {parameter!r} is not bound")
        for parameter in binding["parameter_bindings"]:
            if parameter not in parameters:
                errors.append(f"{intent_id}: unknown parameter {parameter!r}")
        for secret, spec in secrets.items():
            if spec["required"] and secret not in mapped_secrets:
                errors.append(f"{intent_id}: required secret {secret!r} is not bound")
        for secret in mapped_secrets:
            if secret not in secrets:
                errors.append(f"{intent_id}: unknown secret {secret!r}")
        bound_input_artifacts = {
            artifact_id for artifact_ids in mapped_inputs.values() for artifact_id in artifact_ids
        }
        bound_output_artifacts = {
            artifact_id for artifact_ids in mapped_outputs.values() for artifact_id in artifact_ids
        }
        if bound_input_artifacts != set(intents[intent_id]["inputs"]):
            errors.append(
                f"{intent_id}: bound input artifacts do not exactly match the intent inputs"
            )
        if bound_output_artifacts != set(intents[intent_id]["outputs"]):
            errors.append(
                f"{intent_id}: bound output artifacts do not exactly match the intent outputs"
            )

        required_network = intents[intent_id]["required_policy_properties"]["network_access"]
        service_network = descriptor["policies"]["network_access"]
        if required_network == "forbidden" and service_network != "forbidden":
            errors.append(
                f"{intent_id}: network-forbidden intent binds service with {service_network} access"
            )
    return errors


def _format_local_argument(
    value: str, workspace: Path, fixtures: Path, params: dict[str, Any]
) -> str:
    value = value.replace("{workspace}", str(workspace))
    value = value.replace("{fixtures}", str(fixtures))
    for key, parameter in params.items():
        value = value.replace("{" + key + "}", str(parameter))
    return value


def _validate_fixture_tree(root: Path) -> None:
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        suffix = path.suffix.lower()
        if suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif suffix in {".jsonl", ".ndjson"}:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"{path}:{number}: invalid JSONL record") from exc
        elif suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as handle:
                list(csv.DictReader(handle))
        elif suffix in {".yaml", ".yml"}:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        elif suffix == ".pdf" and not path.read_bytes().startswith(b"%PDF-"):
            raise ValueError(f"invalid PDF fixture {path}")
        elif suffix == ".png" and not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"invalid PNG fixture {path}")


def _condition_matches(condition: dict[str, Any], workspace: Path) -> bool:
    path = workspace / condition["path"]
    document = json.loads(path.read_text(encoding="utf-8"))
    return _json_path(document, condition["json_path"]) == condition["equals"]


def _sandbox_profile(
    *, runtime_dir: Path, fixtures: Path, workspace: Path, python_prefix: Path
) -> str:
    """Return a deny-by-default macOS sandbox profile for generated scripts."""

    # CPython and the macOS dynamic loader touch a broad set of system paths at
    # startup. Permit reads generally, then explicitly deny the repository and
    # common credential/user-data locations. The virtual runtime, fixtures and
    # scenario workspace live under a fresh temporary directory and remain
    # readable. Writes are restricted to the scenario workspace.
    home = Path.home().resolve()
    protected = {
        ROOT.resolve(),
        home / ".aws",
        home / ".azure",
        home / ".codex",
        home / ".config",
        home / ".docker",
        home / ".gnupg",
        home / ".kube",
        home / ".ssh",
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "Library",
    }
    # Keep interpreter/runtime paths usable if a user intentionally installs
    # Python beneath one of the broad protected locations.
    protected = {
        path
        for path in protected
        if not python_prefix.resolve().is_relative_to(path)
        and not runtime_dir.resolve().is_relative_to(path)
        and not fixtures.resolve().is_relative_to(path)
        and not workspace.resolve().is_relative_to(path)
    }
    deny_read_rules = "\n".join(
        f"(deny file-read* (subpath {json.dumps(str(path))}))"
        for path in sorted(protected, key=str)
    )
    return (
        "(version 1)\n"
        "(deny default)\n"
        "(allow process*)\n"
        "(allow signal (target self))\n"
        "(allow sysctl-read)\n"
        "(allow mach*)\n"
        "(allow ipc-posix*)\n"
        "(allow system-socket)\n"
        "(allow file-read-metadata)\n"
        "(allow file-read*)\n"
        f"{deny_read_rules}\n"
        "(allow file-write*\n"
        f"    (subpath {json.dumps(str(workspace.resolve()))})\n"
        '    (literal "/dev/null"))\n'
        "(deny network*)\n"
    )


def _run_generated_task(
    *,
    instance_dir: Path,
    script: str,
    arguments: list[str],
    fixtures: Path,
    workspace: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Execute model-produced Python with network/filesystem/resource isolation.

    macOS uses the built-in Seatbelt sandbox. Other platforms require a
    pre-pulled Docker image (``P2SF_SANDBOX_IMAGE``, default
    ``python:3.12-slim``); execution never silently falls back to an
    unrestricted host subprocess.
    """

    runtime_dir = (instance_dir / "runtime").resolve()
    script_path = runtime_dir / script
    clean_env = {
        "HOME": str(workspace),
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "TMPDIR": str(workspace / ".tmp"),
    }
    (workspace / ".tmp").mkdir(exist_ok=True)

    def run_local(command: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a local sandbox command with inherited POSIX resource ceilings."""

        import resource

        def apply_limits() -> None:
            memory_bytes = 512 * 1024 * 1024
            for limit_name in ("RLIMIT_AS", "RLIMIT_DATA", "RLIMIT_RSS"):
                if hasattr(resource, limit_name):
                    limit = getattr(resource, limit_name)
                    try:
                        resource.setrlimit(limit, (memory_bytes, memory_bytes))
                    except (OSError, ValueError):
                        pass
            ceilings = (
                ("RLIMIT_CPU", max(1, timeout_seconds), max(1, timeout_seconds + 1)),
                ("RLIMIT_NPROC", GENERATED_TASK_PIDS, GENERATED_TASK_PIDS),
                ("RLIMIT_NOFILE", 128, 128),
                ("RLIMIT_FSIZE", 64 * 1024 * 1024, 64 * 1024 * 1024),
            )
            for limit_name, soft, hard in ceilings:
                if hasattr(resource, limit_name):
                    try:
                        resource.setrlimit(getattr(resource, limit_name), (soft, hard))
                    except (OSError, ValueError):
                        pass

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=clean_env,
            start_new_session=True,
            preexec_fn=apply_limits,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout_seconds, stdout, stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    if os.environ.get("P2SF_OUTER_SANDBOX") == "1":
        # M5 invokes the validator from inside its already isolated agent
        # container (bounded filesystem, memory, process lifetime, and no
        # direct outbound route). Avoid unsupported nested-container
        # execution while retaining the per-task timeout and clean env.
        return run_local([sys.executable, str(script_path), *arguments])

    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        profile = _sandbox_profile(
            runtime_dir=runtime_dir,
            fixtures=fixtures,
            workspace=workspace,
            python_prefix=Path(sys.base_prefix),
        )
        command = [
            "sandbox-exec",
            "-p",
            profile,
            sys.executable,
            str(script_path),
            *arguments,
        ]
        return run_local(command)

    docker = shutil.which("docker")
    image = os.environ.get("P2SF_SANDBOX_IMAGE", "python:3.12-slim")
    if not docker:
        raise RuntimeError(
            "strong generated-code sandbox unavailable: macOS sandbox-exec or Docker is required"
        )
    inspect = subprocess.run(
        [docker, "image", "inspect", image], capture_output=True, text=True, check=False
    )
    if inspect.returncode:
        raise RuntimeError(
            f"generated-code sandbox image {image!r} is not installed; run: docker pull {image}"
        )
    container_args = [
        item.replace(str(workspace), "/workspace").replace(str(fixtures), "/fixtures")
        for item in arguments
    ]
    command = [
        docker,
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(GENERATED_TASK_PIDS),
        "--memory",
        GENERATED_TASK_MEMORY,
        "--cpus",
        GENERATED_TASK_CPUS,
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-v",
        f"{runtime_dir}:/runtime:ro",
        "-v",
        f"{fixtures.resolve()}:/fixtures:ro",
        "-v",
        f"{workspace.resolve()}:/workspace:rw",
        image,
        "python",
        f"/runtime/{script}",
        *container_args,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )


def _execute_scenarios(
    instance_dir: Path,
    manifest: dict[str, Any],
    *,
    sandbox_generated: bool = False,
    task_timeout_seconds: int = GENERATED_TASK_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    results = []
    for scenario in manifest["scenarios"]:
        fixture_root = scenario.get("fixture_root")
        if fixture_root is None:
            conventional = instance_dir / "fixtures" / "scenarios" / scenario["name"]
            fixtures = (
                conventional if conventional.is_dir() else instance_dir / "fixtures" / "inputs"
            )
        else:
            fixtures = (instance_dir / fixture_root).resolve()
            try:
                fixtures.relative_to(instance_dir.resolve())
            except ValueError as exc:
                raise ValueError(
                    f"scenario {scenario['name']!r} fixture root escapes the instance"
                ) from exc
        if not fixtures.is_dir():
            raise ValueError(
                f"scenario {scenario['name']!r} fixture root does not exist: {fixtures}"
            )
        _validate_fixture_tree(fixtures)
        executed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        with tempfile.TemporaryDirectory(prefix=f"p2sf-{scenario['name']}-") as temp:
            workspace = Path(temp)
            for task in manifest["tasks"]:
                if task.get("local_condition") and not _condition_matches(
                    task["local_condition"], workspace
                ):
                    skipped.append(task["intent_id"])
                    continue
                arguments = [
                    _format_local_argument(item, workspace, fixtures, scenario["parameters"])
                    for item in task["arguments"]
                ]
                try:
                    if sandbox_generated:
                        completed = _run_generated_task(
                            instance_dir=instance_dir,
                            script=task["script"],
                            arguments=arguments,
                            fixtures=fixtures,
                            workspace=workspace,
                            timeout_seconds=task_timeout_seconds,
                        )
                    else:
                        completed = subprocess.run(
                            [
                                sys.executable,
                                str(instance_dir / "runtime" / task["script"]),
                                *arguments,
                            ],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=task_timeout_seconds,
                        )
                except subprocess.TimeoutExpired:
                    errors.append(
                        f"{task['intent_id']}: execution timed out after "
                        f"{task_timeout_seconds} seconds"
                    )
                    break
                if completed.returncode:
                    errors.append(
                        f"{task['intent_id']} (exit {completed.returncode}): "
                        f"{completed.stderr.strip() or completed.stdout.strip() or 'no output'}"
                    )
                    break
                executed.append(task["intent_id"])
            results.append(
                {
                    "scenario": scenario["name"],
                    "status": "pass" if not errors else "fail",
                    "executed_tasks": executed,
                    "skipped_tasks": skipped,
                    "assertions": [],
                    "_errors": errors,
                    "_snapshot": _snapshot_workspace(workspace),
                }
            )
    return results


def _snapshot_workspace(workspace: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(workspace)): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }


def _restore_snapshot(snapshot: dict[str, bytes], root: Path) -> None:
    for relative, content in snapshot.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _evaluate_assertion(assertion: dict[str, Any], workspace: Path) -> tuple[bool, str]:
    path = workspace / assertion["path"]
    assertion_type = assertion["type"]
    if assertion_type == "file_exists":
        passed = path.is_file() and path.stat().st_size > 0
        return passed, f"{path.name} exists and is non-empty" if passed else f"missing {path}"
    if assertion_type == "file_absent":
        passed = not path.exists()
        return passed, f"{path.name} is absent" if passed else f"unexpected file {path}"
    if not path.is_file():
        return False, f"missing {path}"
    if assertion_type.startswith("json_"):
        document = json.loads(path.read_text(encoding="utf-8"))
        value = _json_path(document, assertion["json_path"])
        if assertion_type == "json_path_equals":
            passed = value == assertion["expected"]
            return passed, f"value={value!r}, expected={assertion['expected']!r}"
        if assertion_type == "json_path_gte":
            passed = value >= assertion["minimum"]
            return passed, f"value={value!r}, minimum={assertion['minimum']!r}"
        if assertion_type == "json_array_length":
            passed = len(value) == assertion["expected"]
            return passed, f"length={len(value)}, expected={assertion['expected']}"
    if assertion_type == "csv_row_count":
        with path.open(encoding="utf-8", newline="") as handle:
            count = sum(1 for _ in csv.DictReader(handle))
        if "expected" in assertion:
            passed = count == assertion["expected"]
            return passed, f"rows={count}, expected={assertion['expected']}"
        minimum = assertion["minimum"]
        passed = count >= minimum
        return passed, f"rows={count}, minimum={minimum}"
    return False, f"unsupported assertion type {assertion_type!r}"


def _runtime_graph_errors(
    serviceflow: dict[str, Any], manifest: dict[str, Any], instance_dir: Path
) -> list[str]:
    errors: list[str] = []
    gold_ids = [item["intent_id"] for item in serviceflow["service_intents"]]
    runtime_ids = [item["intent_id"] for item in manifest["tasks"]]
    if len(runtime_ids) != len(set(runtime_ids)):
        errors.append("runtime task identifiers are not unique")
    if set(runtime_ids) != set(gold_ids):
        errors.append(
            "runtime task identities do not match gold service intents: "
            f"runtime={runtime_ids}, gold={gold_ids}"
        )

    known_ids = set(runtime_ids)
    runtime_edges: set[tuple[str, str]] = set()
    for task in manifest["tasks"]:
        intent_id = task["intent_id"]
        for predecessor in task.get("dependencies", []):
            runtime_edges.add((predecessor, intent_id))
        expression = task.get("depends", "")
        for predecessor in known_ids:
            if re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(predecessor)}(?![A-Za-z0-9_])",
                expression,
            ):
                runtime_edges.add((predecessor, intent_id))
        script_path = instance_dir / "runtime" / task["script"]
        if not script_path.is_file():
            errors.append(f"{intent_id}: missing runtime script {task['script']}")
            continue
        try:
            compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec")
        except SyntaxError as exc:
            errors.append(f"{intent_id}: runtime script syntax error: {exc}")

    gold_edges = {(edge["from"], edge["to"]) for edge in serviceflow["control_flow"]["edges"]}
    if runtime_edges != gold_edges:
        errors.append(
            "runtime dependency edges do not match gold control flow: "
            f"missing={sorted(gold_edges - runtime_edges)}, "
            f"extra={sorted(runtime_edges - gold_edges)}"
        )
    return errors


def validate_instance(instance_dir: Path, write_report: bool = True) -> dict[str, Any]:
    instance_dir = instance_dir.resolve()
    serviceflow_path = instance_dir / "gold" / "serviceflow.yaml"
    runtime_path = instance_dir / "runtime" / "manifest.yaml"
    assertions_path = instance_dir / "gold" / "assertions.yaml"
    serviceflow = load_document(serviceflow_path)
    manifest = load_runtime_manifest(instance_dir)
    assertions = load_document(assertions_path)
    catalog_dir = (
        ROOT / "benchmark" / "catalog" / "snapshots" / serviceflow["catalog_snapshot"]["version"]
    )
    catalog = _catalog_index(catalog_dir)

    def g0() -> list[str]:
        errors = []
        required = [
            serviceflow_path,
            runtime_path,
            assertions_path,
            instance_dir / "source" / "source_metadata.yaml",
            instance_dir / "candidates" / "candidate_sets.yaml",
            instance_dir / "gold" / "candidate_labels.yaml",
            instance_dir / "gold" / "bindings.yaml",
            instance_dir / "gold" / "artifact_mappings.yaml",
        ]
        errors.extend(f"missing required file {path}" for path in required if not path.is_file())
        validate_against_schema(
            serviceflow, load_schema(ROOT / "schemas" / "serviceflow_ir.schema.json")
        )
        validate_against_schema(
            manifest, load_schema(ROOT / "schemas" / "runtime_manifest.schema.json")
        )
        validate_against_schema(
            assertions, load_schema(ROOT / "schemas" / "assertions.schema.json")
        )
        source = serviceflow["source"]
        manifest_row = _manifest_row(source)
        for field in [
            "benchmark_id",
            "split",
            "pipeline_id",
            "description_path",
            "description_sha256",
            "internal_spec_path",
            "internal_spec_sha256",
        ]:
            if source.get(field) != manifest_row.get(field):
                errors.append(
                    f"source {field} does not match benchmark manifest: "
                    f"{source.get(field)!r} != {manifest_row.get(field)!r}"
                )
        description = ROOT / "benchmark" / source["description_path"]
        internal_spec = ROOT / "benchmark" / source["internal_spec_path"]
        if _sha256(description) != source["description_sha256"]:
            errors.append("description checksum mismatch")
        if _sha256(internal_spec) != source["internal_spec_sha256"]:
            errors.append("internal-spec checksum mismatch")
        if _sha256(catalog_dir / "catalog.yaml") != serviceflow["catalog_snapshot"]["sha256"]:
            errors.append("catalog checksum mismatch")
        for artifact in serviceflow["artifacts"]:
            schema_ref = artifact.get("schema_ref")
            if not schema_ref:
                continue
            schema_path = instance_dir / schema_ref
            if not schema_path.is_file():
                errors.append(f"missing artifact schema {schema_ref}")
                continue
            load_schema(schema_path)
        binding_projection = load_document(instance_dir / "gold" / "bindings.yaml")
        source_metadata = load_document(instance_dir / "source" / "source_metadata.yaml")
        candidates = load_document(instance_dir / "candidates" / "candidate_sets.yaml")
        candidate_labels = load_document(instance_dir / "gold" / "candidate_labels.yaml")
        mapping_projection = load_document(instance_dir / "gold" / "artifact_mappings.yaml")
        for name, document in [
            ("source/source_metadata.yaml", source_metadata),
            ("candidates/candidate_sets.yaml", candidates),
            ("gold/candidate_labels.yaml", candidate_labels),
            ("gold/bindings.yaml", binding_projection),
            ("gold/artifact_mappings.yaml", mapping_projection),
        ]:
            if document["benchmark_id"] != source["benchmark_id"]:
                errors.append(f"{name} benchmark_id does not match ServiceFlowIR source")
        runtime_scenarios = {item["name"] for item in manifest["scenarios"]}
        assertion_scenarios = {item["scenario"] for item in assertions["scenarios"]}
        if runtime_scenarios != assertion_scenarios:
            errors.append(
                "runtime and assertion scenario sets differ: "
                f"runtime={sorted(runtime_scenarios)}, assertions={sorted(assertion_scenarios)}"
            )
        source_modalities = set(
            source_metadata.get("extension", {}).get("input_modalities", []) or []
        )
        expected_extensions = {
            "pdf": {".pdf"},
            "image": {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"},
        }
        for scenario in manifest["scenarios"]:
            fixture_root = scenario.get("fixture_root")
            if not fixture_root:
                errors.append(f"scenario {scenario['name']!r} has no explicit fixture_root")
                continue
            root = (instance_dir / fixture_root).resolve()
            try:
                root.relative_to(instance_dir)
            except ValueError:
                errors.append(f"scenario {scenario['name']!r} fixture_root escapes the instance")
                continue
            if not root.is_dir():
                errors.append(
                    f"scenario {scenario['name']!r} fixture_root does not exist: {fixture_root}"
                )
                continue
            suffixes = {path.suffix.lower() for path in root.rglob("*") if path.is_file()}
            for modality, extensions in expected_extensions.items():
                if modality in source_modalities and not suffixes.intersection(extensions):
                    errors.append(
                        f"scenario {scenario['name']!r} declares {modality} input "
                        f"but {fixture_root} contains no matching physical file"
                    )
        expected_bindings = [
            {
                "intent_id": item["intent_id"],
                "service_id": item["service_id"],
                "service_version": item["service_version"],
            }
            for item in serviceflow["bindings"]
        ]
        if binding_projection["bindings"] != expected_bindings:
            errors.append("gold/bindings.yaml is stale")

        def project_ports(items: list[dict[str, Any]]) -> dict[str, str | list[str]]:
            projected: dict[str, str | list[str]] = {}
            for item in items:
                current = projected.get(item["port"])
                if current is None:
                    projected[item["port"]] = item["artifact_id"]
                elif isinstance(current, list):
                    current.append(item["artifact_id"])
                else:
                    projected[item["port"]] = [current, item["artifact_id"]]
            return projected

        expected_mappings = [
            {
                "intent_id": item["intent_id"],
                "inputs": project_ports(item["input_bindings"]),
                "outputs": project_ports(item["output_bindings"]),
            }
            for item in serviceflow["bindings"]
        ]
        if mapping_projection["mappings"] != expected_mappings:
            errors.append("gold/artifact_mappings.yaml is stale")
        return errors

    def g1() -> list[str]:
        validate_serviceflow_references(serviceflow)
        spec = load_document(ROOT / "benchmark" / serviceflow["source"]["internal_spec_path"])
        source_steps = {item["step_id"] for item in spec["steps"]}
        accounting = serviceflow.get("source_step_accounting")
        if accounting:
            accounted = {item["source_step_ref"] for item in accounting}
        else:
            accounted = {
                ref
                for intent in serviceflow["service_intents"]
                for ref in intent["source_step_refs"]
            }
        errors = []
        if source_steps - accounted:
            errors.append(f"unaccounted source steps: {sorted(source_steps - accounted)}")
        if accounted - source_steps:
            errors.append(f"unknown source-step refs: {sorted(accounted - source_steps)}")
        if accounting:
            service_accounting = {
                item["source_step_ref"]: set(item["intent_ids"])
                for item in accounting
                if item["disposition"] == "service"
            }
            for intent in serviceflow["service_intents"]:
                for ref in intent["source_step_refs"]:
                    if intent["intent_id"] not in service_accounting.get(ref, set()):
                        errors.append(
                            f"{intent['intent_id']}: source step {ref!r} is not "
                            "service-accounted to this intent"
                        )
        return errors

    def g2() -> list[str]:
        candidates = load_document(instance_dir / "candidates" / "candidate_sets.yaml")
        labels = load_document(instance_dir / "gold" / "candidate_labels.yaml")
        return _validate_candidate_grounding(serviceflow, candidates, labels, catalog)

    def g3() -> list[str]:
        return _validate_contract_closure(serviceflow, catalog)

    def g4() -> list[str]:
        return _runtime_graph_errors(serviceflow, manifest, instance_dir)

    g5_details: dict[str, Any] = {}

    def g5_static() -> list[str]:
        resources = build_resources(instance_dir)
        workflow = resources["workflow"]
        task_count = len(workflow["spec"]["templates"][0]["dag"]["tasks"])
        errors: list[str] = []
        configmap_payloads: list[dict[str, Any]] = []
        if task_count != len(serviceflow["service_intents"]):
            errors.append(
                f"Argo task count {task_count} does not match intent count "
                f"{len(serviceflow['service_intents'])}"
            )
        for document in [workflow, *resources["install_manifest"]]:
            if not document.get("apiVersion") or not document.get("kind"):
                errors.append("generated Kubernetes resource lacks apiVersion/kind")
        for document in resources["install_manifest"]:
            if document.get("kind") != "ConfigMap":
                continue
            size_bytes = _configmap_data_size_bytes(document)
            configmap_payloads.append(
                {
                    "name": document.get("metadata", {}).get("name", "unnamed"),
                    "data_size_bytes": size_bytes,
                    "limit_bytes": CONFIGMAP_DATA_LIMIT_BYTES,
                    "within_limit": size_bytes <= CONFIGMAP_DATA_LIMIT_BYTES,
                }
            )
            if size_bytes > CONFIGMAP_DATA_LIMIT_BYTES:
                name = document.get("metadata", {}).get("name", "unnamed")
                errors.append(
                    f"ConfigMap {name!r} data is {size_bytes} bytes; "
                    f"limit is {CONFIGMAP_DATA_LIMIT_BYTES} bytes"
                )
        workflow_path = instance_dir / "argo" / "workflow.yaml"
        if not workflow_path.is_file() or load_document(workflow_path) != workflow:
            errors.append("argo/workflow.yaml is missing or stale")
        workflow_bundle_path = instance_dir / "argo" / "workflow_bundle.yaml"
        if workflow_bundle_path.is_file():
            workflow_bundle = list(
                yaml.safe_load_all(workflow_bundle_path.read_text(encoding="utf-8"))
            )
            if workflow_bundle != resources["workflow_bundle"]:
                errors.append("argo/workflow_bundle.yaml is stale")
        else:
            errors.append("argo/workflow_bundle.yaml is missing")
        lint_paths = [workflow_path]
        if resources["cronworkflow"]:
            cron_path = instance_dir / "argo" / "cronworkflow.yaml"
            if not cron_path.is_file() or load_document(cron_path) != resources["cronworkflow"]:
                errors.append("argo/cronworkflow.yaml is missing or stale")
            lint_paths.append(cron_path)
            cronworkflow_bundle_path = instance_dir / "argo" / "cronworkflow_bundle.yaml"
            if cronworkflow_bundle_path.is_file():
                cronworkflow_bundle = list(
                    yaml.safe_load_all(cronworkflow_bundle_path.read_text(encoding="utf-8"))
                )
                if cronworkflow_bundle != resources["cronworkflow_bundle"]:
                    errors.append("argo/cronworkflow_bundle.yaml is stale")
            else:
                errors.append("argo/cronworkflow_bundle.yaml is missing")
        install_path = instance_dir / "argo" / "install_manifest.yaml"
        if install_path.is_file():
            installed = list(yaml.safe_load_all(install_path.read_text(encoding="utf-8")))
            if installed != resources["install_manifest"]:
                errors.append("argo/install_manifest.yaml is stale")
        else:
            errors.append("argo/install_manifest.yaml is missing")
        for scenario in manifest["scenarios"]:
            scenario_name = scenario["name"]
            scenario_resources = build_resources(instance_dir, scenario_name=scenario_name)
            scenario_dir = instance_dir / "argo" / "scenarios" / scenario_name
            scenario_workflow_path = scenario_dir / "workflow.yaml"
            if (
                not scenario_workflow_path.is_file()
                or load_document(scenario_workflow_path) != scenario_resources["workflow"]
            ):
                errors.append(f"argo scenario {scenario_name!r} workflow is missing or stale")
            else:
                lint_paths.append(scenario_workflow_path)
            scenario_bundle_path = scenario_dir / "workflow_bundle.yaml"
            if scenario_bundle_path.is_file():
                scenario_bundle = list(
                    yaml.safe_load_all(scenario_bundle_path.read_text(encoding="utf-8"))
                )
                if scenario_bundle != scenario_resources["workflow_bundle"]:
                    errors.append(f"argo scenario {scenario_name!r} workflow bundle is stale")
            else:
                errors.append(f"argo scenario {scenario_name!r} workflow bundle is missing")
            scenario_install_path = scenario_dir / "install_manifest.yaml"
            if scenario_install_path.is_file():
                scenario_install = list(
                    yaml.safe_load_all(scenario_install_path.read_text(encoding="utf-8"))
                )
                if scenario_install != scenario_resources["install_manifest"]:
                    errors.append(f"argo scenario {scenario_name!r} install manifest is stale")
            else:
                errors.append(f"argo scenario {scenario_name!r} install manifest is missing")
            if scenario_resources["cronworkflow"]:
                scenario_cron_path = scenario_dir / "cronworkflow.yaml"
                if (
                    not scenario_cron_path.is_file()
                    or load_document(scenario_cron_path) != scenario_resources["cronworkflow"]
                ):
                    errors.append(
                        f"argo scenario {scenario_name!r} cron workflow is missing or stale"
                    )
                else:
                    lint_paths.append(scenario_cron_path)
                scenario_cron_bundle_path = scenario_dir / "cronworkflow_bundle.yaml"
                if scenario_cron_bundle_path.is_file():
                    scenario_cron_bundle = list(
                        yaml.safe_load_all(scenario_cron_bundle_path.read_text(encoding="utf-8"))
                    )
                    if scenario_cron_bundle != scenario_resources["cronworkflow_bundle"]:
                        errors.append(
                            f"argo scenario {scenario_name!r} cron workflow bundle is stale"
                        )
                else:
                    errors.append(
                        f"argo scenario {scenario_name!r} cron workflow bundle is missing"
                    )
            for document in scenario_resources["install_manifest"]:
                if document.get("kind") != "ConfigMap":
                    continue
                size_bytes = _configmap_data_size_bytes(document)
                configmap_payloads.append(
                    {
                        "name": document.get("metadata", {}).get("name", "unnamed"),
                        "scenario": scenario_name,
                        "data_size_bytes": size_bytes,
                        "limit_bytes": CONFIGMAP_DATA_LIMIT_BYTES,
                        "within_limit": size_bytes <= CONFIGMAP_DATA_LIMIT_BYTES,
                    }
                )
                if size_bytes > CONFIGMAP_DATA_LIMIT_BYTES:
                    errors.append(
                        f"scenario {scenario_name!r} ConfigMap "
                        f"{document.get('metadata', {}).get('name', 'unnamed')!r} is "
                        f"{size_bytes} bytes; limit is {CONFIGMAP_DATA_LIMIT_BYTES} bytes"
                    )
        argo = shutil.which("argo")
        if argo and not errors:
            try:
                completed = subprocess.run(
                    [argo, "lint", "--offline", *[str(path) for path in lint_paths]],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                # A binary for the wrong host architecture is not an available CLI.
                # Preserve this fact in the report without turning deterministic
                # structural validation into a false benchmark failure.
                g5_details["argo_lint"] = {
                    "status": "unavailable",
                    "path": argo,
                    "reason": str(exc),
                }
            else:
                g5_details["argo_lint"] = {
                    "status": "pass" if completed.returncode == 0 else "fail",
                    "path": argo,
                }
                if completed.returncode:
                    errors.append(completed.stdout.strip() or completed.stderr.strip())
        elif not argo:
            g5_details["argo_lint"] = {"status": "unavailable", "reason": "argo not on PATH"}
        g5_details["configmap_payloads"] = configmap_payloads
        return errors

    g5_gate = _run_gate(
        "G5",
        g5_static,
        "Deterministic Argo projection, deployable bundles, ConfigMap-size checks, and structural lint",
    )
    g5_gate["details"] = g5_details
    gates = [
        _run_gate("G0", g0, "Parse, schema, required files, and checksums"),
        _run_gate("G1", g1, "Graph integrity and complete source-step accounting"),
        _run_gate("G2", g2, "Catalog service/version/lifecycle resolution"),
        _run_gate("G3", g3, "Interface, parameter, secret, artifact, and policy closure"),
        _run_gate(
            "G4",
            g4,
            "Exact gold-to-runtime task identities, dependency edges, and script syntax",
        ),
        g5_gate,
    ]

    try:
        scenario_results = _execute_scenarios(instance_dir, manifest)
        execution_errors = [error for result in scenario_results for error in result.pop("_errors")]
    except Exception as exc:
        scenario_results = []
        execution_errors = [str(exc)]

    g6_errors: list[str] = list(execution_errors)
    assertion_sets = {item["scenario"]: item["assertions"] for item in assertions["scenarios"]}
    for result in scenario_results:
        with tempfile.TemporaryDirectory(prefix=f"p2sf-assert-{result['scenario']}-") as temp:
            workspace = Path(temp)
            _restore_snapshot(result.pop("_snapshot"), workspace)
            for assertion in assertion_sets.get(result["scenario"], []):
                passed, message = _evaluate_assertion(assertion, workspace)
                result["assertions"].append(
                    {
                        "assertion_id": assertion["assertion_id"],
                        "status": "pass" if passed else "fail",
                        "message": message,
                    }
                )
                if not passed:
                    g6_errors.append(f"{result['scenario']}:{assertion['assertion_id']}: {message}")
            executed = set(result["executed_tasks"])
            for artifact in serviceflow["artifacts"]:
                producer = artifact["producer"]
                schema_ref = artifact.get("schema_ref")
                producers = (
                    []
                    if producer is None
                    else producer
                    if isinstance(producer, list)
                    else [producer]
                )
                if not any(item in executed for item in producers) or not schema_ref:
                    continue
                artifact_path = workspace / "artifacts" / f"{artifact['artifact_id']}.json"
                assertion_id = f"schema_{artifact['artifact_id']}"
                try:
                    document = json.loads(artifact_path.read_text(encoding="utf-8"))
                    validate_against_schema(document, load_schema(instance_dir / schema_ref))
                    passed, message = True, "artifact conforms to its reviewed JSON Schema"
                except Exception as exc:
                    passed, message = False, str(exc)
                    g6_errors.append(f"{result['scenario']}:{assertion_id}: {message}")
                result["assertions"].append(
                    {
                        "assertion_id": assertion_id,
                        "status": "pass" if passed else "fail",
                        "message": message,
                    }
                )
        if any(item["status"] == "fail" for item in result["assertions"]):
            result["status"] = "fail"
    gates.append(
        {
            "gate": "G6",
            "status": "pass" if not g6_errors else "fail",
            "checks": [
                "Execute every declared scenario and evaluate reviewed semantic assertions and artifact schemas"
            ],
            "errors": g6_errors,
        }
    )

    report = {
        "report_version": "0.1.0",
        "pipeline_id": serviceflow["source"]["benchmark_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "pass" if all(item["status"] == "pass" for item in gates) else "fail",
        "gates": gates,
        "scenario_results": scenario_results,
    }
    validate_against_schema(report, load_schema(ROOT / "schemas" / "validation_report.schema.json"))
    if write_report:
        report_path = instance_dir / "validation" / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance_dir", type=Path)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = validate_instance(args.instance_dir, write_report=not args.no_write)
    for gate in report["gates"]:
        print(f"{gate['gate']}: {gate['status']}")
        for error in gate["errors"]:
            print(f"  - {error}")
    if report["overall_status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
