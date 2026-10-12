"""Public submission validation (G0-G5 + G6-Exec) and deterministic compilation.

Implements the public half of the validator split in
``plan_experiement_evals.md`` Sections 6-7. ``validate_submission`` runs
gold-free gates over a candidate submission inside an isolated workspace and
returns structured diagnostics suitable for the M4 repair loop and the M5
agent. It never reads gold artifacts, candidate labels, assertions, or review
records, and it never reports assertion outcomes (G6-Assert is evaluation-only
and lives in the private scorer).

Submission package contract (methods M3/M4/M5)::

    submission/
      serviceflow.yaml        # ServiceFlowIR, validated against workspace schemas/
      runtime/
        manifest.yaml         # runtime manifest, validated against workspace schemas/
        scripts/*.py          # mock task scripts referenced by the manifest
      argo/                   # written by the compile tool (generated projection)

Gate mapping follows the paper (not the benchmark self-validator):

- G0 parse/schema validity: package presence, YAML/JSON parsing, schema
  conformance, script presence/syntax, artifact-schema and fixture-root
  resolution.
- G1 service-graph validity: IR cross-references, cycle freedom, and
  consistency between the IR control flow and the runtime manifest graph.
- G2 catalog grounding: bound services exist in the workspace catalog at the
  bound version and are lifecycle-active.
- G3 binding compatibility: ports, cardinality, data types, required
  inputs/outputs/parameters, and intent artifact exact-match.
- G4 policy compliance: secret binding closure and network-access policy
  compatibility.
- G5 orchestration compilation: deterministic projection succeeds and the
  generated Argo resources pass structural checks (and ``argo lint --offline``
  when the binary is available).
- G6-Exec: scenarios execute to completion on public fixture inputs and the
  produced artifacts conform to the public contract schemas. No assertions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from prompt2serviceflow.compiler.argo import build_resources, write_resources
from prompt2serviceflow.experiments.runtime_compiler import materialize_runtime
from prompt2serviceflow.validators.instance_validation import (
    CONFIGMAP_DATA_LIMIT_BYTES,
    _catalog_index,
    _configmap_data_size_bytes,
    _execute_scenarios,
    _restore_snapshot,
)
from prompt2serviceflow.validators.schema_validation import (
    SemanticValidationError,
    format_json_path,
    load_document,
    validate_serviceflow_references,
)

TOOL_NAME = "validate_submission"
TOOL_VERSION = "2.0.0"
REPORT_VERSION = "0.2.0"

GATE_ORDER = ("G0", "G1", "G2", "G3", "G4", "G5", "G6-Exec")

GATE_DESCRIPTIONS = {
    "G0": "Parse/schema validity of the submission package",
    "G1": "Service-graph validity and IR/manifest graph consistency",
    "G2": "Catalog grounding of bound services",
    "G3": "Binding compatibility with service interfaces and contracts",
    "G4": "Policy compliance (secrets, network access)",
    "G5": "Deterministic orchestration compilation and structural Argo validity",
    "G6-Exec": "Scenario execution on public fixtures and artifact schema conformance",
}


def _diagnostic(code: str, message: str, path: str | None = None) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {"code": code, "message": message}
    if path is not None:
        diagnostic["path"] = path
    return diagnostic


def _schema_diagnostics(
    code: str, document: Any, schema: dict[str, Any], path: str
) -> list[dict[str, Any]]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    return [
        _diagnostic(code, f"{format_json_path(error.absolute_path)}: {error.message}", path)
        for error in errors
    ]


def _load_json_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cycle_exists(nodes: list[str], edges: list[tuple[str, str]]) -> str | None:
    """Return a cyclic node id if the directed graph has a cycle (Kahn)."""
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    indegree: dict[str, int] = {node: 0 for node in nodes}
    for source, target in edges:
        if source in adjacency and target in indegree and target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1
    queue = [node for node in nodes if indegree[node] == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(nodes):
        remaining = [node for node in nodes if indegree[node] > 0]
        return remaining[0] if remaining else None
    return None


def _manifest_edges(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    known_ids = {task["intent_id"] for task in manifest["tasks"]}
    edges: set[tuple[str, str]] = set()
    for task in manifest["tasks"]:
        intent_id = task["intent_id"]
        for predecessor in task.get("dependencies", []) or []:
            edges.add((predecessor, intent_id))
        expression = task.get("depends", "") or ""
        for predecessor in known_ids:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(predecessor)}(?![A-Za-z0-9_])", expression):
                edges.add((predecessor, intent_id))
    return edges


class _SubmissionContext:
    """Loaded submission/workspace state shared across gates."""

    def __init__(self, workspace_dir: Path, submission_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()
        self.submission_dir = submission_dir.resolve()
        self.serviceflow: dict[str, Any] | None = None
        self.manifest: dict[str, Any] | None = None
        self.catalog: dict[tuple[str, str], dict[str, Any]] | None = None
        # Set by G0: downstream gates run only on schema-valid documents.
        self.serviceflow_valid = False
        self.manifest_valid = False

    @property
    def serviceflow_path(self) -> Path:
        return self.submission_dir / "serviceflow.yaml"

    @property
    def manifest_path(self) -> Path:
        return self.submission_dir / "runtime" / "manifest.yaml"

    def load_catalog(self) -> dict[tuple[str, str], dict[str, Any]]:
        if self.catalog is None:
            self.catalog = _catalog_index(self.workspace_dir / "catalog")
        return self.catalog


def _assemble_virtual_instance(context: _SubmissionContext, target_dir: Path) -> Path:
    """Assemble the instance-shaped layout the compiler/executor expect.

    The compiler and scenario executor are instance-relative: they require
    ``runtime/``, ``fixtures/``, and ``contracts/`` under one root. The
    virtual instance combines submission-owned runtime artifacts with
    workspace-owned public fixtures and contracts. Nothing gold-adjacent is
    involved because workspaces never contain it.
    """
    instance_dir = target_dir / "instance"
    runtime_dir = instance_dir / "runtime"
    runtime_dir.mkdir(parents=True)
    shutil.copy2(context.manifest_path, runtime_dir / "manifest.yaml")
    scripts_source = context.submission_dir / "runtime" / "scripts"
    if scripts_source.is_dir():
        shutil.copytree(scripts_source, runtime_dir / "scripts")
    for name in ("fixtures", "contracts"):
        source = context.workspace_dir / name
        if source.is_dir():
            shutil.copytree(source, instance_dir / name)
    return instance_dir


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def _gate_g0(context: _SubmissionContext) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    schemas_dir = context.workspace_dir / "schemas"

    if not context.serviceflow_path.is_file():
        diagnostics.append(
            _diagnostic(
                "G0_MISSING_FILE",
                "submission/serviceflow.yaml is missing",
                "submission/serviceflow.yaml",
            )
        )
    else:
        try:
            context.serviceflow = load_document(context.serviceflow_path)
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    "G0_PARSE_ERROR",
                    f"serviceflow.yaml does not parse: {exc}",
                    "submission/serviceflow.yaml",
                )
            )
        else:
            schema_path = schemas_dir / "serviceflow_ir.schema.json"
            schema_diagnostics = _schema_diagnostics(
                "G0_SCHEMA_ERROR",
                context.serviceflow,
                _load_json_schema(schema_path),
                "submission/serviceflow.yaml",
            )
            diagnostics.extend(schema_diagnostics)
            context.serviceflow_valid = not schema_diagnostics

    if not context.manifest_path.is_file():
        diagnostics.append(
            _diagnostic(
                "G0_MISSING_FILE",
                "submission/runtime/manifest.yaml is missing",
                "submission/runtime/manifest.yaml",
            )
        )
    else:
        try:
            context.manifest = load_document(context.manifest_path)
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    "G0_PARSE_ERROR",
                    f"runtime/manifest.yaml does not parse: {exc}",
                    "submission/runtime/manifest.yaml",
                )
            )
        else:
            schema_path = schemas_dir / "runtime_manifest.schema.json"
            schema_diagnostics = _schema_diagnostics(
                "G0_SCHEMA_ERROR",
                context.manifest,
                _load_json_schema(schema_path),
                "submission/runtime/manifest.yaml",
            )
            diagnostics.extend(schema_diagnostics)
            context.manifest_valid = not schema_diagnostics

    if context.manifest is not None:
        for task in context.manifest.get("tasks", []):
            script = context.submission_dir / "runtime" / task["script"]
            relative = f"submission/runtime/{task['script']}"
            if not script.is_file():
                diagnostics.append(
                    _diagnostic(
                        "G0_SCRIPT_MISSING",
                        f"{task['intent_id']}: missing runtime script {task['script']}",
                        relative,
                    )
                )
                continue
            try:
                py_compile.compile(str(script), doraise=True)
            except py_compile.PyCompileError as exc:
                diagnostics.append(
                    _diagnostic(
                        "G0_SCRIPT_SYNTAX",
                        f"{task['intent_id']}: runtime script syntax error: {exc}",
                        relative,
                    )
                )

    if context.serviceflow is not None:
        for artifact in context.serviceflow.get("artifacts", []):
            schema_ref = artifact.get("schema_ref")
            if not schema_ref:
                continue
            schema_path = (context.workspace_dir / schema_ref).resolve()
            try:
                schema_path.relative_to(context.workspace_dir)
            except ValueError:
                diagnostics.append(
                    _diagnostic(
                        "G0_ARTIFACT_SCHEMA_MISSING",
                        f"artifact {artifact['artifact_id']}: schema_ref escapes the "
                        f"workspace: {schema_ref}",
                        schema_ref,
                    )
                )
                continue
            if not schema_path.is_file():
                diagnostics.append(
                    _diagnostic(
                        "G0_ARTIFACT_SCHEMA_MISSING",
                        f"artifact {artifact['artifact_id']}: missing schema {schema_ref}",
                        schema_ref,
                    )
                )
                continue
            try:
                _load_json_schema(schema_path)
            except Exception as exc:
                diagnostics.append(
                    _diagnostic(
                        "G0_ARTIFACT_SCHEMA_INVALID",
                        f"artifact {artifact['artifact_id']}: invalid schema: {exc}",
                        schema_ref,
                    )
                )

    if context.manifest is not None:
        for scenario in context.manifest.get("scenarios", []):
            fixture_root = scenario.get("fixture_root")
            candidate = fixture_root or f"fixtures/scenarios/{scenario['name']}"
            root = (context.workspace_dir / candidate).resolve()
            try:
                root.relative_to(context.workspace_dir)
            except ValueError:
                diagnostics.append(
                    _diagnostic(
                        "G0_FIXTURE_ROOT_ESCAPE",
                        f"scenario {scenario['name']!r} fixture_root escapes the workspace",
                        candidate,
                    )
                )
                continue
            if not root.is_dir():
                fallback = context.workspace_dir / "fixtures" / "inputs"
                if fixture_root is not None or not fallback.is_dir():
                    diagnostics.append(
                        _diagnostic(
                            "G0_FIXTURE_ROOT_MISSING",
                            f"scenario {scenario['name']!r} fixture root does not exist: "
                            f"{candidate}",
                            candidate,
                        )
                    )
    return diagnostics


def _gate_g1(context: _SubmissionContext) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    serviceflow = context.serviceflow
    if serviceflow is None or not context.serviceflow_valid:
        return [_diagnostic("G1_SKIPPED", "G0 did not produce a valid ServiceFlowIR document")]

    try:
        validate_serviceflow_references(serviceflow)
    except SemanticValidationError as exc:
        diagnostics.extend(
            _diagnostic("G1_REFERENCE_ERROR", message, "submission/serviceflow.yaml")
            for message in exc.errors
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic("G1_REFERENCE_ERROR", str(exc), "submission/serviceflow.yaml")
        )

    intent_ids = [item["intent_id"] for item in serviceflow["service_intents"]]
    edges = [(edge["from"], edge["to"]) for edge in serviceflow["control_flow"]["edges"]]
    cyclic = _cycle_exists(intent_ids, edges)
    if cyclic is not None:
        diagnostics.append(
            _diagnostic("G1_CYCLE", f"control-flow graph contains a cycle involving {cyclic!r}")
        )

    if context.manifest is not None and context.manifest_valid:
        manifest_ids = [task["intent_id"] for task in context.manifest["tasks"]]
        if len(manifest_ids) != len(set(manifest_ids)):
            diagnostics.append(
                _diagnostic("G1_TASK_ID_DUPLICATE", "runtime task identifiers are not unique")
            )
        if set(manifest_ids) != set(intent_ids):
            diagnostics.append(
                _diagnostic(
                    "G1_MANIFEST_IDENTITY_MISMATCH",
                    "runtime task identities do not match service intents: "
                    f"runtime={sorted(manifest_ids)}, intents={sorted(intent_ids)}",
                )
            )
        ir_edges = set(edges)
        runtime_edges = _manifest_edges(context.manifest)
        if runtime_edges != ir_edges:
            diagnostics.append(
                _diagnostic(
                    "G1_MANIFEST_EDGE_MISMATCH",
                    "runtime dependency edges do not match control flow: "
                    f"missing={sorted(ir_edges - runtime_edges)}, "
                    f"extra={sorted(runtime_edges - ir_edges)}",
                )
            )
        cyclic_manifest = _cycle_exists(manifest_ids, sorted(runtime_edges))
        if cyclic_manifest is not None:
            diagnostics.append(
                _diagnostic(
                    "G1_CYCLE",
                    f"runtime dependency graph contains a cycle involving {cyclic_manifest!r}",
                )
            )
    return diagnostics


def _gate_g2(context: _SubmissionContext) -> list[dict[str, Any]]:
    if context.serviceflow is None or not context.serviceflow_valid:
        return [_diagnostic("G2_SKIPPED", "G0 did not produce a valid ServiceFlowIR document")]
    catalog = context.load_catalog()
    diagnostics: list[dict[str, Any]] = []

    # Anchor the submission to the workspace catalog it was grounded against.
    # The workspace catalog is sanitized, so the anchor is the version plus
    # the digest of the sanitized catalog.yaml (both in workspace.yaml).
    workspace_index = context.workspace_dir / "catalog" / "catalog.yaml"
    if workspace_index.is_file():
        workspace_document = yaml.safe_load(workspace_index.read_text(encoding="utf-8"))
        declared = context.serviceflow.get("catalog_snapshot") or {}
        if declared.get("version") != workspace_document.get("version"):
            diagnostics.append(
                _diagnostic(
                    "G2_CATALOG_VERSION_MISMATCH",
                    f"declared catalog snapshot {declared.get('version')!r} does not "
                    f"match workspace catalog {workspace_document.get('version')!r}",
                )
            )
        actual_sha = hashlib.sha256(workspace_index.read_bytes()).hexdigest()
        if declared.get("sha256") and declared["sha256"] != actual_sha:
            diagnostics.append(
                _diagnostic(
                    "G2_CATALOG_CHECKSUM_MISMATCH",
                    "declared catalog sha256 does not match the sanitized workspace "
                    "catalog (see catalog.sanitized_catalog_yaml_sha256 in workspace.yaml)",
                )
            )
    for binding in context.serviceflow["bindings"]:
        key = (binding["service_id"], binding["service_version"])
        descriptor = catalog.get(key)
        if descriptor is None:
            diagnostics.append(
                _diagnostic(
                    "G2_UNRESOLVED_SERVICE",
                    f"unresolved service {key[0]}:{key[1]} in the workspace catalog",
                )
            )
        elif descriptor["lifecycle"]["status"] != "active":
            diagnostics.append(
                _diagnostic(
                    "G2_INACTIVE_SERVICE",
                    f"service {key[0]} lifecycle status is "
                    f"{descriptor['lifecycle']['status']!r}, not 'active'",
                )
            )
    return diagnostics


def _binding_maps(binding: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    mapped_inputs: dict[str, list[str]] = {}
    for item in binding["input_bindings"]:
        mapped_inputs.setdefault(item["port"], []).append(item["artifact_id"])
    mapped_outputs: dict[str, list[str]] = {}
    for item in binding["output_bindings"]:
        mapped_outputs.setdefault(item["port"], []).append(item["artifact_id"])
    return mapped_inputs, mapped_outputs


def _gate_g3(context: _SubmissionContext) -> list[dict[str, Any]]:
    if context.serviceflow is None or not context.serviceflow_valid:
        return [_diagnostic("G3_SKIPPED", "G0 did not produce a valid ServiceFlowIR document")]
    catalog = context.load_catalog()
    serviceflow = context.serviceflow
    artifacts = {item["artifact_id"]: item for item in serviceflow["artifacts"]}
    intents = {item["intent_id"]: item for item in serviceflow["service_intents"]}
    diagnostics: list[dict[str, Any]] = []
    for binding in serviceflow["bindings"]:
        descriptor = catalog.get((binding["service_id"], binding["service_version"]))
        if descriptor is None:
            continue  # G2 reports the unresolved service.
        intent_id = binding["intent_id"]
        interface = descriptor["interface"]
        input_ports = {item["name"]: item for item in interface["inputs"]}
        output_ports = {item["name"]: item for item in interface["outputs"]}
        parameters = {item["name"]: item for item in interface["parameters"]}
        mapped_inputs, mapped_outputs = _binding_maps(binding)

        for port, artifact_ids in mapped_inputs.items():
            if port not in input_ports:
                diagnostics.append(
                    _diagnostic(
                        "G3_UNKNOWN_INPUT_PORT", f"{intent_id}: unknown input port {port!r}"
                    )
                )
                continue
            if input_ports[port]["cardinality"] != "many" and len(artifact_ids) != 1:
                diagnostics.append(
                    _diagnostic(
                        "G3_INPUT_CARDINALITY",
                        f"{intent_id}: input port {port!r} does not accept multiple artifacts",
                    )
                )
            for artifact_id in artifact_ids:
                artifact = artifacts.get(artifact_id)
                if artifact is None:
                    continue  # G1 reports unknown artifact references.
                if artifact["data_type"] != input_ports[port]["data_type"]:
                    diagnostics.append(
                        _diagnostic(
                            "G3_INPUT_TYPE_MISMATCH",
                            f"{intent_id}: input {port!r} expects "
                            f"{input_ports[port]['data_type']}, "
                            f"got {artifact['data_type']}",
                        )
                    )
        for port, artifact_ids in mapped_outputs.items():
            if port not in output_ports:
                diagnostics.append(
                    _diagnostic(
                        "G3_UNKNOWN_OUTPUT_PORT", f"{intent_id}: unknown output port {port!r}"
                    )
                )
                continue
            if output_ports[port]["cardinality"] != "many" and len(artifact_ids) != 1:
                diagnostics.append(
                    _diagnostic(
                        "G3_OUTPUT_CARDINALITY",
                        f"{intent_id}: output port {port!r} does not accept multiple artifacts",
                    )
                )
            for artifact_id in artifact_ids:
                artifact = artifacts.get(artifact_id)
                if artifact is None:
                    continue
                if artifact["data_type"] != output_ports[port]["data_type"]:
                    diagnostics.append(
                        _diagnostic(
                            "G3_OUTPUT_TYPE_MISMATCH",
                            f"{intent_id}: output {port!r} expects "
                            f"{output_ports[port]['data_type']}, "
                            f"got {artifact['data_type']}",
                        )
                    )
        for port, spec in input_ports.items():
            if spec["required"] and port not in mapped_inputs:
                diagnostics.append(
                    _diagnostic(
                        "G3_REQUIRED_INPUT_UNBOUND",
                        f"{intent_id}: required input port {port!r} is not bound",
                    )
                )
        for port, spec in output_ports.items():
            if spec["required"] and port not in mapped_outputs:
                diagnostics.append(
                    _diagnostic(
                        "G3_REQUIRED_OUTPUT_UNBOUND",
                        f"{intent_id}: required output port {port!r} is not bound",
                    )
                )
        bound_parameters = set(binding["parameter_bindings"])
        for parameter, spec in parameters.items():
            if spec["required"] and parameter not in bound_parameters:
                diagnostics.append(
                    _diagnostic(
                        "G3_REQUIRED_PARAMETER_UNBOUND",
                        f"{intent_id}: required parameter {parameter!r} is not bound",
                    )
                )
        for parameter in sorted(bound_parameters):
            if parameter not in parameters:
                diagnostics.append(
                    _diagnostic(
                        "G3_UNKNOWN_PARAMETER", f"{intent_id}: unknown parameter {parameter!r}"
                    )
                )
        intent = intents.get(intent_id)
        if intent is not None:
            bound_input_artifacts = {
                artifact_id for ids in mapped_inputs.values() for artifact_id in ids
            }
            bound_output_artifacts = {
                artifact_id for ids in mapped_outputs.values() for artifact_id in ids
            }
            if bound_input_artifacts != set(intent["inputs"]):
                diagnostics.append(
                    _diagnostic(
                        "G3_INPUT_ARTIFACT_MISMATCH",
                        f"{intent_id}: bound input artifacts do not exactly match "
                        "the intent inputs",
                    )
                )
            if bound_output_artifacts != set(intent["outputs"]):
                diagnostics.append(
                    _diagnostic(
                        "G3_OUTPUT_ARTIFACT_MISMATCH",
                        f"{intent_id}: bound output artifacts do not exactly match "
                        "the intent outputs",
                    )
                )
    return diagnostics


def _gate_g4(context: _SubmissionContext) -> list[dict[str, Any]]:
    if context.serviceflow is None or not context.serviceflow_valid:
        return [_diagnostic("G4_SKIPPED", "G0 did not produce a valid ServiceFlowIR document")]
    catalog = context.load_catalog()
    serviceflow = context.serviceflow
    intents = {item["intent_id"]: item for item in serviceflow["service_intents"]}
    diagnostics: list[dict[str, Any]] = []
    for binding in serviceflow["bindings"]:
        descriptor = catalog.get((binding["service_id"], binding["service_version"]))
        if descriptor is None:
            continue
        intent_id = binding["intent_id"]
        secrets = {item["name"]: item for item in descriptor["interface"]["secrets"]}
        mapped_secrets = {item["secret"] for item in binding["secret_bindings"]}
        for secret, spec in secrets.items():
            if spec["required"] and secret not in mapped_secrets:
                diagnostics.append(
                    _diagnostic(
                        "G4_REQUIRED_SECRET_UNBOUND",
                        f"{intent_id}: required secret {secret!r} is not bound",
                    )
                )
        for secret in sorted(mapped_secrets):
            if secret not in secrets:
                diagnostics.append(
                    _diagnostic("G4_UNKNOWN_SECRET", f"{intent_id}: unknown secret {secret!r}")
                )
        intent = intents.get(intent_id)
        if intent is None:
            continue
        required_network = intent["required_policy_properties"]["network_access"]
        service_network = descriptor["policies"]["network_access"]
        if required_network == "forbidden" and service_network != "forbidden":
            diagnostics.append(
                _diagnostic(
                    "G4_NETWORK_POLICY",
                    f"{intent_id}: network-forbidden intent binds service with "
                    f"{service_network} access",
                )
            )
    return diagnostics


def _gate_g5(context: _SubmissionContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    details: dict[str, Any] = {}
    if context.manifest is None or not context.manifest_valid:
        return [_diagnostic("G5_SKIPPED", "G0 did not produce a valid runtime manifest")], details
    diagnostics: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="p2sf-g5-") as temp:
        instance_dir = _assemble_virtual_instance(context, Path(temp))
        try:
            resource_sets = {"base": build_resources(instance_dir)}
            for scenario in context.manifest["scenarios"]:
                resource_sets[scenario["name"]] = build_resources(
                    instance_dir, scenario_name=scenario["name"]
                )
        except Exception as exc:
            return [
                _diagnostic("G5_COMPILE_ERROR", f"deterministic compilation failed: {exc}")
            ], details

        configmap_payloads: list[dict[str, Any]] = []
        for label, resources in resource_sets.items():
            workflow = resources["workflow"]
            documents = [workflow, *resources["install_manifest"]]
            for document in documents:
                if not document.get("apiVersion") or not document.get("kind"):
                    diagnostics.append(
                        _diagnostic(
                            "G5_RESOURCE_MALFORMED",
                            f"{label}: generated resource lacks apiVersion/kind",
                        )
                    )
            for document in resources["install_manifest"]:
                if document.get("kind") != "ConfigMap":
                    continue
                size_bytes = _configmap_data_size_bytes(document)
                name = document.get("metadata", {}).get("name", "unnamed")
                configmap_payloads.append(
                    {
                        "name": name,
                        "scenario": label,
                        "data_size_bytes": size_bytes,
                        "limit_bytes": CONFIGMAP_DATA_LIMIT_BYTES,
                        "within_limit": size_bytes <= CONFIGMAP_DATA_LIMIT_BYTES,
                    }
                )
                if size_bytes > CONFIGMAP_DATA_LIMIT_BYTES:
                    diagnostics.append(
                        _diagnostic(
                            "G5_CONFIGMAP_LIMIT",
                            f"{label}: ConfigMap {name!r} data is {size_bytes} bytes; "
                            f"limit is {CONFIGMAP_DATA_LIMIT_BYTES} bytes",
                        )
                    )
        if context.serviceflow is not None and context.serviceflow_valid:
            task_count = len(
                resource_sets["base"]["workflow"]["spec"]["templates"][0]["dag"]["tasks"]
            )
            intent_count = len(context.serviceflow["service_intents"])
            if task_count != intent_count:
                diagnostics.append(
                    _diagnostic(
                        "G5_TASK_COUNT_MISMATCH",
                        f"compiled task count {task_count} does not match intent "
                        f"count {intent_count}",
                    )
                )
        details["configmap_payloads"] = configmap_payloads

        argo = shutil.which("argo")
        if argo and not diagnostics:
            written = write_resources(instance_dir)
            lint_paths = [written["workflow"]]
            if (instance_dir / "argo" / "cronworkflow.yaml").is_file():
                lint_paths.append(instance_dir / "argo" / "cronworkflow.yaml")
            try:
                completed = subprocess.run(
                    [argo, "lint", "--offline", *[str(path) for path in lint_paths]],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                details["argo_lint"] = {"status": "unavailable", "reason": str(exc)}
            else:
                details["argo_lint"] = {
                    "status": "pass" if completed.returncode == 0 else "fail",
                }
                if completed.returncode:
                    diagnostics.append(
                        _diagnostic(
                            "G5_LINT_FAIL", completed.stdout.strip() or completed.stderr.strip()
                        )
                    )
        elif not argo:
            details["argo_lint"] = {"status": "unavailable", "reason": "argo not on PATH"}
    return diagnostics, details


def _gate_g6_exec(context: _SubmissionContext) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    details: dict[str, Any] = {"scenarios": []}
    if context.manifest is None or not context.manifest_valid:
        return [_diagnostic("G6_SKIPPED", "G0 did not produce a valid runtime manifest")], details
    diagnostics: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="p2sf-g6-") as temp:
        instance_dir = _assemble_virtual_instance(context, Path(temp))
        try:
            scenario_results = _execute_scenarios(
                instance_dir, context.manifest, sandbox_generated=True
            )
        except Exception as exc:
            return [_diagnostic("G6_EXEC_ERROR", f"scenario execution failed: {exc}")], details
        for result in scenario_results:
            errors = result.pop("_errors")
            snapshot = result.pop("_snapshot")
            result.pop("assertions", None)  # assertion outcomes are evaluation-only
            for error in errors:
                diagnostics.append(_diagnostic("G6_EXEC_ERROR", f"{result['scenario']}: {error}"))
            executed = set(result["executed_tasks"])
            if context.serviceflow is not None and context.serviceflow_valid and not errors:
                with tempfile.TemporaryDirectory(
                    prefix=f"p2sf-g6-artifacts-{result['scenario']}-"
                ) as artifact_temp:
                    workspace = Path(artifact_temp)
                    _restore_snapshot(snapshot, workspace)
                    for artifact in context.serviceflow["artifacts"]:
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
                        label = f"{result['scenario']}:{artifact['artifact_id']}"
                        if not artifact_path.is_file():
                            diagnostics.append(
                                _diagnostic(
                                    "G6_ARTIFACT_MISSING",
                                    f"{label}: expected artifact was not produced",
                                )
                            )
                            continue
                        try:
                            document = json.loads(artifact_path.read_text(encoding="utf-8"))
                        except Exception as exc:
                            diagnostics.append(
                                _diagnostic(
                                    "G6_ARTIFACT_SCHEMA_INVALID",
                                    f"{label}: artifact does not parse: {exc}",
                                )
                            )
                            continue
                        schema_path = (context.workspace_dir / schema_ref).resolve()
                        try:
                            artifact_schema = _load_json_schema(schema_path)
                        except Exception as exc:
                            diagnostics.append(
                                _diagnostic(
                                    "G6_ARTIFACT_SCHEMA_INVALID",
                                    f"{label}: cannot load schema {schema_ref!r}: {exc}",
                                    schema_ref,
                                )
                            )
                            continue
                        schema_errors = _schema_diagnostics(
                            "G6_ARTIFACT_SCHEMA_INVALID",
                            document,
                            artifact_schema,
                            schema_ref,
                        )
                        for item in schema_errors:
                            item["message"] = f"{label}: {item['message']}"
                        diagnostics.extend(schema_errors)
            details["scenarios"].append(result)
    return diagnostics, details


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _run_gate(name: str, check: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    try:
        diagnostics = check()
    except Exception as exc:  # Uniform failure surface for repair consumers.
        diagnostics = [_diagnostic(f"{name}_INTERNAL_ERROR", str(exc))]
    skipped = any(item["code"].endswith("_SKIPPED") for item in diagnostics) and not any(
        not item["code"].endswith("_SKIPPED") for item in diagnostics
    )
    failed = any(not item["code"].endswith("_SKIPPED") for item in diagnostics)
    status = "skipped" if skipped else "fail" if failed else "pass"
    return {
        "gate": name,
        "status": status,
        "description": GATE_DESCRIPTIONS[name],
        "diagnostics": diagnostics,
    }


def validate_submission(
    workspace_dir: Path,
    submission_dir: Path | None = None,
    *,
    run_execution: bool = True,
) -> dict[str, Any]:
    """Run public gates G0-G5 (+ G6-Exec) over a submission in a workspace."""
    workspace_dir = workspace_dir.resolve()
    submission_dir = (submission_dir or workspace_dir / "submission").resolve()
    context = _SubmissionContext(workspace_dir, submission_dir)

    gates: list[dict[str, Any]] = []
    g0 = _run_gate("G0", lambda: _gate_g0(context))
    gates.append(g0)
    gates.append(_run_gate("G1", lambda: _gate_g1(context)))
    gates.append(_run_gate("G2", lambda: _gate_g2(context)))
    gates.append(_run_gate("G3", lambda: _gate_g3(context)))
    gates.append(_run_gate("G4", lambda: _gate_g4(context)))

    try:
        g5_diagnostics, g5_details = _gate_g5(context)
    except Exception as exc:
        g5_diagnostics, g5_details = [_diagnostic("G5_INTERNAL_ERROR", str(exc))], {}
    g5 = _run_gate("G5", lambda: g5_diagnostics)
    g5["details"] = g5_details
    gates.append(g5)

    if run_execution:
        try:
            g6_diagnostics, g6_details = _gate_g6_exec(context)
        except Exception as exc:
            g6_diagnostics, g6_details = (
                [_diagnostic("G6_INTERNAL_ERROR", str(exc))],
                {"scenarios": []},
            )
        g6 = _run_gate("G6-Exec", lambda: g6_diagnostics)
        g6["details"] = g6_details
    else:
        g6 = {
            "gate": "G6-Exec",
            "status": "skipped",
            "description": GATE_DESCRIPTIONS["G6-Exec"],
            "diagnostics": [_diagnostic("G6_SKIPPED", "execution disabled (--no-exec)")],
        }
    gates.append(g6)

    first_failing = next((gate["gate"] for gate in gates if gate["status"] == "fail"), None)
    return {
        "report_version": REPORT_VERSION,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_dir),
        "submission": str(submission_dir),
        "overall_status": "pass" if first_failing is None else "fail",
        "first_failing_gate": first_failing,
        "gates": gates,
    }


def compile_submission(
    workspace_dir: Path,
    submission_dir: Path | None = None,
    out_dir: Path | None = None,
) -> dict[str, str]:
    """Deterministically project a submission to Argo resources.

    Returns a mapping of resource kind to written path. Raises on compilation
    failure; callers wanting diagnostics should use ``validate_submission``.
    """
    workspace_dir = workspace_dir.resolve()
    submission_dir = (submission_dir or workspace_dir / "submission").resolve()
    context = _SubmissionContext(workspace_dir, submission_dir)
    materialize_runtime(workspace_dir, submission_dir)
    context.manifest = load_document(context.manifest_path)
    out_dir = (out_dir or submission_dir / "argo").resolve()
    with tempfile.TemporaryDirectory(prefix="p2sf-compile-") as temp:
        instance_dir = _assemble_virtual_instance(context, Path(temp))
        written = write_resources(instance_dir)
        argo_source = instance_dir / "argo"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(argo_source, out_dir)
    return {kind: str(out_dir / path.name) for kind, path in written.items()}


# ---------------------------------------------------------------------------
# CLIs
# ---------------------------------------------------------------------------


def _validate_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_submission",
        description="Public gold-free submission validation (G0-G5 + G6-Exec).",
    )
    parser.add_argument("--workspace", type=Path, required=True, help="workspace root")
    parser.add_argument(
        "--submission",
        type=Path,
        default=None,
        help="submission dir (default: <workspace>/submission)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument(
        "--no-exec", action="store_true", help="skip G6-Exec (structural gates only)"
    )
    parser.add_argument("--quiet", action="store_true", help="only print the overall status")
    return parser.parse_args(argv)


def validate_main(argv: list[str] | None = None) -> int:
    args = _validate_args(argv)
    report = validate_submission(args.workspace, args.submission, run_execution=not args.no_exec)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        for gate in report["gates"]:
            print(f"{gate['gate']}: {gate['status']}")
            for diagnostic in gate["diagnostics"]:
                print(f"  - [{diagnostic['code']}] {diagnostic['message']}")
        print(f"overall: {report['overall_status']}")
    else:
        print(report["overall_status"])
    return 0 if report["overall_status"] == "pass" else 1


def _compile_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="compile",
        description="Deterministic ServiceFlowIR -> Argo projection for a submission.",
    )
    parser.add_argument("--workspace", type=Path, required=True, help="workspace root")
    parser.add_argument(
        "--submission",
        type=Path,
        default=None,
        help="submission dir (default: <workspace>/submission)",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="output dir (default: <submission>/argo)"
    )
    return parser.parse_args(argv)


def compile_main(argv: list[str] | None = None) -> int:
    args = _compile_args(argv)
    try:
        written = compile_submission(args.workspace, args.submission, args.out)
    except Exception as exc:
        print(f"compile failed: {exc}", file=sys.stderr)
        return 1
    for kind, path in sorted(written.items()):
        print(f"generated {kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(validate_main())
