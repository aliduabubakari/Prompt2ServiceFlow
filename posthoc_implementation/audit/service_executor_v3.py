"""Small, explicit service executor for isolated invocation diagnostics.

No benchmark answers, reference programs, network clients, or mock fallbacks.
Only the operation subsets in REGISTRY are supported. Unknown behavior raises
UnsupportedOperation; malformed inputs raise ValueError. This is deliberately
not a whole-workflow executor or a replacement for the published compiler.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re

from retention_adapter import resolve


class UnsupportedOperation(ValueError):
    pass


REGISTRY = {
    "retention_cutoff_config_resolver": {
        "version": "1.0.0", "inputs": {"runtime_parameters"},
        "optional_inputs": {"runtime_variables"},
        "outputs": {"retention_config", "config_status"},
        "parameters": {"max_age_parameter_name", "max_age_variable_name", "default_max_age_days",
                       "enable_delete", "print_deletes", "reference_time"}},
    "csv_tabular_schema_validating_loader": {
        "version": "1.0.0", "inputs": {"csv_file"}, "optional_inputs": set(),
        "outputs": {"validated_dataset", "validated_data_object", "validation_status"},
        "parameters": {"required_columns", "has_header", "delimiter", "fail_on_empty",
                       "output_path", "expected_schema"}},
    "structured_json_to_csv_exporter": {
        "version": "1.0.0", "inputs": {"structured_json"}, "optional_inputs": set(),
        "outputs": {"csv_file", "export_status"},
        "parameters": {"output_filename", "dataset_id", "columns", "include_header", "delimiter"}},
}


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("Unsafe or unsupported artifact identifier")
    return value


def inside(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Path must be relative and contained")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path escapes its root")
    return target


def artifact_suffix(artifact: dict) -> str:
    if artifact.get("media_type") == "text/csv" or artifact.get("data_type") == "csv":
        return ".csv"
    return ".json"


def output_alias(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Explicit output path is required")
    if value.startswith("/workspace/artifacts/"):
        value = value[len("/workspace/artifacts/"):]
    elif value.startswith("artifacts/"):
        value = value[len("artifacts/"):]
    inside(Path("/virtual-artifacts"), value)
    return value


def delimiter(parameters: dict) -> str:
    value = parameters.get("delimiter", ",")
    if value not in (",", ";", "\t", "|"):
        raise ValueError("Unsupported delimiter value")
    return value


def boolean(parameters: dict, name: str, default: bool) -> bool:
    value = parameters.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be Boolean")
    return value


def columns(value) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(c, str) and c for c in value):
        raise ValueError("Columns must be a list of non-empty names")
    if len(set(value)) != len(value):
        raise ValueError("Duplicate columns are ambiguous")
    return value


def compute(service: str, parameters: dict, inputs: dict, uris: dict) -> dict:
    """Compute port values from supplied inputs, without any output-schema examples."""
    definition = REGISTRY[service]
    unknown = set(parameters) - definition["parameters"]
    if unknown:
        raise UnsupportedOperation(f"Unimplemented parameter semantics: {sorted(unknown)}")
    if service == "retention_cutoff_config_resolver":
        value = resolve(parameters, inputs["runtime_parameters"], inputs.get("runtime_variables", {}))
        value["delete_enabled"] = value["enable_delete"]
        return {"retention_config": value,
                "config_status": {"success": True, "errors": [], "max_age_days": value["max_age_days"],
                                  "source": value["source"]}}
    if service == "csv_tabular_schema_validating_loader":
        output_alias(parameters.get("output_path"))
        if not boolean(parameters, "has_header", True):
            raise UnsupportedOperation("Headerless CSV mapping is not implemented")
        if parameters.get("expected_schema"):
            raise UnsupportedOperation("Typed/nullable expected_schema rules are not implemented")
        reader = csv.DictReader(io.StringIO(inputs["csv_file"]), delimiter=delimiter(parameters), strict=True)
        header = columns(reader.fieldnames or [])
        required = columns(parameters.get("required_columns", []))
        if not set(required).issubset(header):
            raise ValueError("CSV is missing required columns")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("CSV row width differs from its header")
        if not rows and boolean(parameters, "fail_on_empty", False):
            raise ValueError("Empty CSV rejected by fail_on_empty")
        source = uris["csv_file"]
        dataset = {"columns": header, "rows": rows, "row_count": len(rows), "valid": True,
                   "source_uri": source}
        return {"validated_dataset": dataset,
                "validated_data_object": {"source_uri": source, "record_count": len(rows),
                                          "row_count": len(rows), "columns": header, "success": True},
                "validation_status": {"success": True, "parse_success": True, "schema_valid": True,
                                      "rows_read": len(rows), "columns": header, "errors": []}}
    if service != "structured_json_to_csv_exporter":
        raise UnsupportedOperation("Unregistered service")
    output_alias(parameters.get("output_filename"))
    data = inputs["structured_json"]
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("Structured JSON requires rows and columns")
    header = columns(data.get("columns"))
    rows = data["rows"]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Each structured row must be an object")
    selected = columns(parameters.get("columns", header))
    for name in selected:
        if name not in header and not any(name in row for row in rows):
            raise ValueError("Requested CSV column is absent")
    if "dataset_id" in parameters and "dataset_id" in data and parameters["dataset_id"] != data["dataset_id"]:
        raise ValueError("Dataset identifier mismatch")
    if any(isinstance(row.get(name), (dict, list)) for row in rows for name in selected):
        raise UnsupportedOperation("Nested CSV cell serialization is not specified")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=delimiter(parameters), lineterminator="\n")
    if boolean(parameters, "include_header", True):
        writer.writerow(selected)
    for row in rows:
        writer.writerow([row.get(name, "") for name in selected])
    return {"csv_file": stream.getvalue(),
            "export_status": {"success": True, "rows_read": len(rows), "rows_written": len(rows),
                              "columns_exported": selected, "output_uri": parameters["output_filename"],
                              "errors": []}}


def project(value: dict, schema: dict | None) -> dict:
    if not schema:
        return value
    # A required field with no computation is an explicit limitation, never a
    # request to insert a constant, minimum, or hidden expected answer.
    if schema.get("type") != "object" or "$ref" in schema:
        raise UnsupportedOperation("Only direct object output schemas are supported")
    missing = set(schema.get("required", [])) - value.keys()
    if missing:
        raise UnsupportedOperation(f"Unimplemented required output fields: {sorted(missing)}")
    if schema.get("additionalProperties") is False:
        return {k: v for k, v in value.items() if k in schema.get("properties", {})}
    return value


def run(spec: dict, workspace: Path, fixtures: Path) -> dict:
    """Run one isolated invocation. No upstream mock artifacts are accepted."""
    inputs, uris = {}, {}
    for port, bound in spec["inputs"].items():
        path = inside(fixtures, bound["relative"])
        raw = path.read_text(encoding="utf-8")
        inputs[port] = raw if bound["suffix"] == ".csv" else json.loads(raw)
        uris[port] = bound["fixture_ref"]
    values = compute(spec["service_id"], spec["parameters"], inputs, uris)
    pending = {}
    for output in spec["outputs"]:
        port = output["port"]
        value = values[port]
        if port == "csv_file":
            encoded = value
        else:
            encoded = json.dumps(project(value, output.get("schema")), indent=2) + "\n"
        name = identifier(output["artifact_id"]) + output["suffix"]
        if name in pending:
            raise ValueError("Output artifact collision")
        pending[name] = encoded
    alias_parameter = {"csv_tabular_schema_validating_loader": ("output_path", "validated_dataset"),
                       "structured_json_to_csv_exporter": ("output_filename", "csv_file")}.get(spec["service_id"])
    if alias_parameter:
        param, port = alias_parameter
        alias = output_alias(spec["parameters"][param])
        output = next(o for o in spec["outputs"] if o["port"] == port)
        content = pending[output["artifact_id"] + output["suffix"]]
        if alias in pending and pending[alias] != content:
            raise ValueError("Output filename conflicts with another bound artifact")
        pending[alias] = content
    for name, encoded in pending.items():
        target = inside(workspace / "artifacts", name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
    return values


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(json.loads(args.spec.read_text()), args.workspace, args.fixtures)
    except UnsupportedOperation as exc:
        print(f"UNSUPPORTED_OPERATION: {exc}")
        raise SystemExit(3)
    except (ValueError, KeyError, OSError, csv.Error, TypeError) as exc:
        print(f"INVOCATION_REJECTED: {type(exc).__name__}: {exc}")
        raise SystemExit(2)
