"""One public-service adapter, independent of private assertions/reference code.

Implements the published retention resolver's documented parameter > variable
> default precedence and reference-time arithmetic. It refuses missing inputs
or unspecified logical time rather than filling in hidden expected values.
The follow-up runner copies this standalone module into the sandbox runtime.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

SERVICE = ("retention_cutoff_config_resolver", "1.0.0")


def resolve(parameters: dict, runtime_parameters: dict, runtime_variables: dict) -> dict:
    name = parameters["max_age_parameter_name"]
    variable = parameters.get("max_age_variable_name")
    if name in runtime_parameters and runtime_parameters[name] is not None:
        age, source = runtime_parameters[name], "parameter"
    elif variable and variable in runtime_variables and runtime_variables[variable] is not None:
        age, source = runtime_variables[variable], "variable"
    else:
        age, source = parameters["default_max_age_days"], "default"
    if isinstance(age, bool) or not isinstance(age, int) or age < 0:
        raise ValueError("Resolved retention age must be a non-negative integer")
    reference = parameters.get("reference_time")
    if not reference:
        raise ValueError("Explicit reference_time is required; no hidden or wall-clock fallback")
    stamp = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("reference_time must include a timezone")
    for flag in ("enable_delete", "print_deletes"):
        if flag in parameters and not isinstance(parameters[flag], bool):
            raise ValueError(f"{flag} must be Boolean")
    cutoff = stamp - timedelta(days=age)
    return {"max_age_days": age, "source": source,
            "cutoff_timestamp": cutoff.isoformat(), "cutoff_date": cutoff.date().isoformat(),
            "enable_delete": parameters.get("enable_delete", False),
            "print_deletes": parameters.get("print_deletes", False)}


def project(value: dict, port: str, schema: dict | None) -> dict:
    if port == "retention_config":
        result = {k: v for k, v in value.items()}
        # The local public artifact schema names the deletion flag
        # delete_enabled, while the service descriptor calls it enable_delete.
        result["delete_enabled"] = result["enable_delete"]
    elif port == "config_status":
        result = {"success": True, "errors": [], "max_age_days": value["max_age_days"],
                  "source": value["source"]}
    else:
        raise ValueError(f"Unsupported retention output port: {port}")
    if schema:
        if schema.get("type") != "object" or "$ref" in schema:
            raise ValueError("Only direct object schemas are supported by this adapter")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            result = {k: v for k, v in result.items() if k in properties}
        missing = set(schema.get("required", [])) - result.keys()
        if missing:
            raise ValueError(f"Adapter cannot compute required output fields: {sorted(missing)}")
    return result


def fixture_relative(reference: str) -> Path:
    parts = Path(reference).parts
    if parts[:2] == ("fixtures", "inputs"):
        relative = Path(*parts[2:])
    elif len(parts) > 3 and parts[:2] == ("fixtures", "scenarios"):
        relative = Path(*parts[3:])
    else:
        raise ValueError("Unsupported external input fixture mapping")
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Invalid external input fixture mapping")
    return relative


def _input(spec: dict, port: str, workspace: Path, fixtures: Path) -> dict:
    bound = spec["inputs"].get(port)
    if bound is None:
        if port == "runtime_variables":
            return {}
        raise ValueError("Required runtime_parameters port has no binding")
    if bound.get("upstream"):
        path = workspace / "artifacts" / (bound["artifact_id"] + ".json")
    else:
        relative = fixture_relative(bound["fixture_ref"])
        path = fixtures / relative
        if not path.resolve().is_relative_to(fixtures.resolve()):
            raise ValueError("Input fixture path escapes fixture root")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Retention inputs must be JSON objects")
    return value


def run(spec: dict, workspace: Path, fixtures: Path) -> dict:
    value = resolve(spec["parameters"], _input(spec, "runtime_parameters", workspace, fixtures),
                    _input(spec, "runtime_variables", workspace, fixtures))
    target = workspace / "artifacts"
    target.mkdir(exist_ok=True, parents=True)
    for output in spec["outputs"]:
        path = target / (output["artifact_id"] + ".json")
        if not path.resolve().is_relative_to(target.resolve()):
            raise ValueError("Output path escapes artifact directory")
        path.write_text(json.dumps(project(value, output["port"], output.get("schema")), indent=2) + "\n")
    return value
