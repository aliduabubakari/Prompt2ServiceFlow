"""V2 candidate executor: explicit output namespaces, no v1/v3 modifications.

Service operations retain the verified deterministic subset from audit v3.
Only path/binding semantics change. Requested service locations are logical
container labels, never permission to write absolute paths on the host.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

import service_executor_v3 as base

EXECUTOR_VERSION = "2.0.0-candidate.1"
CONTRACT_VERSION = "2.0.0"
REGISTRY = base.REGISTRY
UnsupportedOperation = base.UnsupportedOperation
identifier = base.identifier
inside = base.inside
artifact_suffix = base.artifact_suffix
delimiter = base.delimiter


def logical_path(value: str) -> str:
    """Injectively map a logical POSIX location into a private relative namespace.

    Distinguish absolute and relative labels. Do not collapse '..', expand a
    scheduler template, fetch a URI, guess a basename, or touch a host path.
    """
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError("Non-empty logical output location required")
    if any(token in value for token in ("\\", "\x00", "{", "}", "$", "://")):
        raise UnsupportedOperation("Unresolved template or URI output location")
    raw = value.split("/")
    if any(part in (".", "..") for part in raw):
        raise ValueError("Traversal and dot segments are forbidden")
    if value.endswith("/") or "//" in value:
        raise ValueError("Output location must name one unambiguous file")
    path = PurePosixPath(value)
    parts = path.parts[1:] if path.is_absolute() else path.parts
    if not parts:
        raise ValueError("Output location must name a file")
    result = ("absolute/" if path.is_absolute() else "relative/") + "/".join(parts)
    inside(Path("/logical-output-namespace"), result)
    return result


def compute(service: str, parameters: dict, inputs: dict, uris: dict) -> dict:
    # The old compute routine also checked v3 output-path syntax. Supply it a
    # checked relative label, then retain the original logical URI in status.
    # Do not alter input data, parameter values that affect computation, or
    # unknown-operation rejection behavior.
    translated = dict(parameters)
    path_parameter = {"csv_tabular_schema_validating_loader": "output_path",
                      "structured_json_to_csv_exporter": "output_filename"}.get(service)
    if path_parameter:
        translated[path_parameter] = logical_path(parameters.get(path_parameter))
    values = base.compute(service, translated, inputs, uris)
    if service == "structured_json_to_csv_exporter":
        values["export_status"]["output_uri"] = parameters["output_filename"]
    return values


def plan_writes(spec: dict, values: dict) -> tuple[dict[str, bytes], dict]:
    """Compute all target bytes before writing, retaining each port's identity.

    Canonical bindings use artifacts/<id>.<suffix>. Requested service output
    locations use service_outputs/<intent>/<port>/<absolute|relative>/<label>.
    Thus the same filename in two roles can never overwrite a different port.
    """
    intent = identifier(spec["intent_id"])
    writes, by_port = {}, {}
    for output in spec["outputs"]:
        port = identifier(output["port"])
        if port in by_port:
            raise ValueError("Duplicate output port")
        suffix = output["suffix"]
        if suffix not in (".json", ".csv"):
            raise UnsupportedOperation("Unsupported output format")
        if port == "csv_file":
            if suffix != ".csv":
                raise ValueError("CSV output port must bind a CSV artifact")
            encoded = values[port].encode("utf-8")
        else:
            if suffix != ".json":
                raise ValueError("Object output port must bind a JSON artifact")
            encoded = (json.dumps(base.project(values[port], output.get("schema")), indent=2) + "\n").encode()
        canonical = "artifacts/" + identifier(output["artifact_id"]) + suffix
        if canonical in writes:
            raise ValueError("Output bindings collide")
        writes[canonical] = encoded
        by_port[port] = {"port": port, "artifact_id": output["artifact_id"],
                         "canonical_path": canonical, "sha256": hashlib.sha256(encoded).hexdigest()}
    path_binding = {
        "csv_tabular_schema_validating_loader": ("output_path", "validated_dataset"),
        "structured_json_to_csv_exporter": ("output_filename", "csv_file"),
    }.get(spec["service_id"])
    if path_binding:
        parameter, port = path_binding
        label = spec["parameters"][parameter]
        relative = "service_outputs/" + intent + "/" + port + "/" + logical_path(label)
        target = by_port[port]
        writes[relative] = writes[target["canonical_path"]]
        target.update(requested_location=label, materialized_path=relative)
    mapping = {"contract_version": CONTRACT_VERSION, "executor_version": EXECUTOR_VERSION,
               "intent_id": intent, "outputs": list(by_port.values())}
    writes["logs/public_output_bindings.json"] = (json.dumps(mapping, indent=2) + "\n").encode()
    return writes, mapping


def run(spec: dict, workspace: Path, fixtures: Path) -> dict:
    inputs, uris = {}, {}
    for port, bound in spec["inputs"].items():
        raw = inside(fixtures, bound["relative"]).read_text(encoding="utf-8")
        inputs[port] = raw if bound["suffix"] == ".csv" else json.loads(raw)
        uris[port] = bound["fixture_ref"]
    values = compute(spec["service_id"], spec["parameters"], inputs, uris)
    writes, _ = plan_writes(spec, values)
    # Preflight every target before materializing any files. A symlink cannot
    # redirect even a logical absolute output outside the temporary workspace.
    targets = {relative: inside(workspace, relative) for relative in writes}
    for relative, path in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(writes[relative])
    return values
