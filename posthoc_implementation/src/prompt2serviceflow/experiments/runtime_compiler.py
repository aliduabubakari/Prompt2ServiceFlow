"""Gold-free deterministic ServiceFlowIR runtime materialization.

The experiment asks M3-M5 to solve service composition, not to invent a
second program for every benchmark cell.  This module projects a submitted
ServiceFlowIR into the small local mock runtime used by the public gates.  It
reads only the submission and the allowlisted workspace (schemas, contracts,
and fixtures); gold bindings and private assertions are never inputs.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


RUNTIME_COMPILER_VERSION = "1.0.0"


def _schema_example(schema: dict[str, Any]) -> Any:
    """Create a deterministic, schema-valid example for the public mock."""

    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    for keyword in ("oneOf", "anyOf"):
        alternatives = schema.get(keyword)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                candidate = _schema_example(alternative)
                if Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(candidate):
                    return candidate

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "null")
    if schema_type is None:
        schema_type = "object" if "properties" in schema else "string"

    if schema_type == "object":
        properties = schema.get("properties") or {}
        required = list(schema.get("required") or [])
        # These optional status fields make the public mock informative while
        # remaining fully determined by the public contract.
        for helpful in ("success", "errors"):
            if helpful in properties and helpful not in required:
                required.append(helpful)
        return {name: _schema_example(properties.get(name, {})) for name in required}
    if schema_type == "array":
        count = int(schema.get("minItems", 0))
        return [_schema_example(schema.get("items") or {}) for _ in range(count)]
    if schema_type == "integer":
        return int(schema.get("minimum", 0))
    if schema_type == "number":
        return float(schema.get("minimum", 0))
    if schema_type == "boolean":
        return True
    if schema_type == "null":
        return None
    formats = {
        "date": "2024-01-01",
        "date-time": "2024-01-01T00:00:00Z",
        "email": "mock@example.invalid",
        "hostname": "example.invalid",
        "ipv4": "192.0.2.1",
        "ipv6": "2001:db8::1",
        "uri": "https://example.invalid/resource",
        "uuid": "00000000-0000-4000-8000-000000000000",
    }
    value = formats.get(schema.get("format"), "example")
    minimum = int(schema.get("minLength", 0))
    if len(value) < minimum:
        value += "x" * (minimum - len(value))
    return value


def _fixture_scenarios(workspace: Path) -> list[dict[str, Any]]:
    scenarios_root = workspace / "fixtures" / "scenarios"
    if scenarios_root.is_dir():
        scenarios = [
            {
                "name": path.name,
                "parameters": {},
                "fixture_root": f"fixtures/scenarios/{path.name}",
            }
            for path in sorted(scenarios_root.iterdir())
            if path.is_dir() and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", path.name)
        ]
        if scenarios:
            return scenarios
    if (workspace / "fixtures" / "inputs").is_dir():
        return [{"name": "nominal", "parameters": {}, "fixture_root": "fixtures/inputs"}]
    raise ValueError("workspace has no public fixture directory")


def _cron(serviceflow: dict[str, Any]) -> dict[str, str] | None:
    schedule = serviceflow.get("schedule") or {}
    if schedule.get("type") != "cron" or not schedule.get("expression"):
        return None
    aliases = {
        "@hourly": "0 * * * *",
        "@daily": "0 0 * * *",
        "@weekly": "0 0 * * 0",
        "@monthly": "0 0 1 * *",
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
    }
    expression = str(schedule["expression"])
    return {
        "schedule": aliases.get(expression, expression),
        "timezone": str(schedule.get("timezone") or "UTC"),
    }


def _script_text(outputs: list[dict[str, Any]]) -> str:
    payload = json.dumps(outputs, sort_keys=True, separators=(",", ":"))
    return f'''#!/usr/bin/env python3
"""Generated deterministic public-contract mock."""
from __future__ import annotations
import argparse
import csv
import json
import shutil
from pathlib import Path

OUTPUTS = json.loads({payload!r})

def _first_fixture(root: Path, suffix: str) -> Path | None:
    return next((path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix == suffix), None)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for output in OUTPUTS:
        artifact_id = output["artifact_id"]
        data_type = output["data_type"]
        if output.get("json_value") is not None:
            (artifacts / f"{{artifact_id}}.json").write_text(
                json.dumps(output["json_value"], indent=2) + "\\n", encoding="utf-8"
            )
        elif data_type in ("csv", "table"):
            source = _first_fixture(args.fixtures, ".csv")
            target = artifacts / f"{{artifact_id}}.csv"
            if source:
                shutil.copyfile(source, target)
            else:
                with target.open("w", encoding="utf-8", newline="") as handle:
                    csv.writer(handle).writerow(["value"])
        elif data_type in ("binary", "image") or output.get("media_type") == "application/pdf":
            suffix = ".pdf" if output.get("media_type") == "application/pdf" else ".bin"
            (artifacts / f"{{artifact_id}}{{suffix}}").write_bytes(b"Prompt2ServiceFlow deterministic mock\\n")
        else:
            suffix = ".md" if data_type == "markdown" else ".txt"
            (artifacts / f"{{artifact_id}}{{suffix}}").write_text("example\\n", encoding="utf-8")

if __name__ == "__main__":
    main()
'''


def materialize_runtime(
    workspace: Path,
    submission: Path | None = None,
    *,
    replace: bool = True,
) -> list[Path]:
    """Compile ``serviceflow.yaml`` into a deterministic runtime package."""

    workspace = workspace.resolve()
    submission = (submission or workspace / "submission").resolve()
    serviceflow_path = submission / "serviceflow.yaml"
    if not serviceflow_path.is_file():
        raise FileNotFoundError(f"missing ServiceFlowIR: {serviceflow_path}")
    serviceflow = yaml.safe_load(serviceflow_path.read_text(encoding="utf-8"))
    if not isinstance(serviceflow, dict):
        raise ValueError("serviceflow.yaml must contain one mapping")

    artifacts = {item["artifact_id"]: item for item in serviceflow.get("artifacts", [])}
    predecessors: dict[str, list[str]] = {
        item["intent_id"]: [] for item in serviceflow.get("service_intents", [])
    }
    for edge in (serviceflow.get("control_flow") or {}).get("edges", []):
        predecessors.setdefault(edge["to"], []).append(edge["from"])

    tasks: list[dict[str, Any]] = []
    scripts: dict[str, str] = {}
    for index, intent in enumerate(serviceflow.get("service_intents", []), start=1):
        intent_id = intent["intent_id"]
        script_name = f"{index:03d}_{intent_id}.py"
        output_specs: list[dict[str, Any]] = []
        for artifact_id in intent.get("outputs", []):
            artifact = artifacts.get(artifact_id)
            if not artifact:
                continue
            spec = {
                "artifact_id": artifact_id,
                "data_type": artifact.get("data_type", "json"),
                "media_type": artifact.get("media_type"),
            }
            schema_ref = artifact.get("schema_ref")
            if schema_ref:
                schema_path = (workspace / schema_ref).resolve()
                schema_path.relative_to(workspace)
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                example = _schema_example(schema)
                errors = list(
                    Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(example)
                )
                if errors:
                    raise ValueError(
                        f"cannot materialize public contract {schema_ref}: {errors[0].message}"
                    )
                spec["json_value"] = example
            output_specs.append(spec)
        scripts[script_name] = _script_text(output_specs)
        task: dict[str, Any] = {
            "intent_id": intent_id,
            "script": f"scripts/{script_name}",
            "arguments": ["--workspace", "{workspace}", "--fixtures", "{fixtures}"],
            "retries": 0,
        }
        dependencies = sorted(set(predecessors.get(intent_id, [])))
        if dependencies:
            task["dependencies"] = dependencies
        tasks.append(task)

    if not tasks:
        raise ValueError("ServiceFlowIR has no service intents")
    manifest: dict[str, Any] = {
        "runtime_manifest_version": "0.1.0",
        "pipeline_id": serviceflow.get("composition_id"),
        "image": "python:3.12-slim",
        "workflow_parameters": [],
        "tasks": tasks,
        "scenarios": _fixture_scenarios(workspace),
    }
    cron = _cron(serviceflow)
    if cron:
        manifest["cron"] = cron

    runtime = submission / "runtime"
    if replace and runtime.exists():
        shutil.rmtree(runtime)
    scripts_dir = runtime / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = runtime / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    written = [manifest_path]
    for name, content in scripts.items():
        path = scripts_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        written.append(path)
    return written
