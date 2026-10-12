"""JSON Schema and cross-reference validation for Prompt2ServiceFlow artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


class SemanticValidationError(ValueError):
    """Raised when a document is structurally valid but internally inconsistent."""

    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    raise ValueError(f"Unsupported document type: {path}")


def load_schema(path: Path) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def format_json_path(parts: Iterable[Any]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def validate_against_schema(document: Any, schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path))
    if errors:
        messages = [
            f"{format_json_path(error.absolute_path)}: {error.message}" for error in errors
        ]
        raise SemanticValidationError(messages)


def duplicate_values(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def validate_service_descriptor_semantics(document: dict[str, Any]) -> None:
    errors: list[str] = []
    interface = document["interface"]

    for section in ("inputs", "outputs", "parameters", "secrets"):
        names = [item["name"] for item in interface[section]]
        duplicates = duplicate_values(names)
        if duplicates:
            errors.append(f"interface.{section} contains duplicate names: {duplicates}")

    target_names = {
        document["service_id"],
        *(item["name"] for item in interface["inputs"]),
        *(item["name"] for item in interface["outputs"]),
        *(item["name"] for item in interface["parameters"]),
    }
    contract_ids = [item["contract_id"] for item in document["contracts"]]
    duplicates = duplicate_values(contract_ids)
    if duplicates:
        errors.append(f"contracts contains duplicate contract IDs: {duplicates}")
    for contract in document["contracts"]:
        if contract["target"] not in target_names:
            errors.append(
                f"contract {contract['contract_id']!r} targets unknown interface member "
                f"{contract['target']!r}"
            )

    if document["policies"]["secret_access"] == "forbidden" and interface["secrets"]:
        errors.append("secret_access is forbidden but the interface declares secrets")
    if document["policies"]["network_access"] == "forbidden" and document["policies"].get(
        "allowed_network_targets"
    ):
        errors.append("network_access is forbidden but allowed_network_targets is non-empty")

    if errors:
        raise SemanticValidationError(errors)


def validate_serviceflow_references(document: dict[str, Any]) -> None:
    errors: list[str] = []
    intents = {item["intent_id"]: item for item in document["service_intents"]}
    artifacts = {item["artifact_id"]: item for item in document["artifacts"]}
    systems = {item["system_id"]: item for item in document["external_systems"]}

    for label, values in (
        ("service_intents", [item["intent_id"] for item in document["service_intents"]]),
        ("artifacts", [item["artifact_id"] for item in document["artifacts"]]),
        ("external_systems", [item["system_id"] for item in document["external_systems"]]),
        ("bindings", [item["intent_id"] for item in document["bindings"]]),
    ):
        duplicates = duplicate_values(values)
        if duplicates:
            errors.append(f"{label} contains duplicate IDs: {duplicates}")

    def require_intent(value: str, context: str) -> None:
        if value not in intents:
            errors.append(f"{context} references unknown intent {value!r}")

    def require_artifact(value: str, context: str) -> None:
        if value not in artifacts:
            errors.append(f"{context} references unknown artifact {value!r}")

    def require_system(value: str, context: str) -> None:
        if value not in systems:
            errors.append(f"{context} references unknown external system {value!r}")

    for intent in document["service_intents"]:
        intent_id = intent["intent_id"]
        for artifact_id in intent["inputs"]:
            require_artifact(artifact_id, f"intent {intent_id!r} input")
        for artifact_id in intent["outputs"]:
            require_artifact(artifact_id, f"intent {intent_id!r} output")
        for system_id in intent["external_system_refs"]:
            require_system(system_id, f"intent {intent_id!r}")

    accounting = document.get("source_step_accounting", [])
    accounting_refs = [item["source_step_ref"] for item in accounting]
    duplicates = duplicate_values(accounting_refs)
    if duplicates:
        errors.append(f"source_step_accounting contains duplicate refs: {duplicates}")
    for item in accounting:
        intent_ids = item["intent_ids"]
        if item["disposition"] == "service" and not intent_ids:
            errors.append(
                f"service-accounted step {item['source_step_ref']!r} has no intent IDs"
            )
        if item["disposition"] != "service" and intent_ids:
            errors.append(
                f"{item['disposition']}-accounted step {item['source_step_ref']!r} "
                "must not name service intents"
            )
        for intent_id in intent_ids:
            require_intent(intent_id, f"source-step accounting {item['source_step_ref']!r}")
            intent = intents.get(intent_id)
            if intent and item["source_step_ref"] not in intent["source_step_refs"]:
                errors.append(
                    f"source-step accounting {item['source_step_ref']!r} names intent "
                    f"{intent_id!r}, but that intent does not reference the source step"
                )

    for edge in document["control_flow"]["edges"]:
        require_intent(edge["from"], "control-flow edge")
        require_intent(edge["to"], "control-flow edge")
        if edge["from"] == edge["to"]:
            errors.append(f"control-flow edge contains a self-loop at {edge['from']!r}")

    for group in document["control_flow"]["parallel_groups"]:
        for intent_id in group["intent_ids"]:
            require_intent(intent_id, f"parallel group {group['group_id']!r}")

    for branch in document["control_flow"]["branches"]:
        require_intent(branch["decision_intent"], f"branch {branch['branch_id']!r}")
        if branch.get("decision_artifact"):
            require_artifact(branch["decision_artifact"], f"branch {branch['branch_id']!r}")
            decision_intent = intents.get(branch["decision_intent"])
            if (
                decision_intent
                and branch["decision_artifact"] not in decision_intent["outputs"]
            ):
                errors.append(
                    f"branch {branch['branch_id']!r} decision artifact "
                    f"{branch['decision_artifact']!r} is not produced by "
                    f"{branch['decision_intent']!r}"
                )
        for case in branch["cases"]:
            for intent_id in case["next_intents"]:
                require_intent(intent_id, f"branch case {case['case_id']!r}")
        if branch.get("merge_intent"):
            require_intent(branch["merge_intent"], f"branch {branch['branch_id']!r}")

    for gate in document["control_flow"]["gates"]:
        require_intent(gate["sensor_intent"], f"gate {gate['gate_id']!r}")
        for intent_id in gate["gated_intents"]:
            require_intent(intent_id, f"gate {gate['gate_id']!r}")

    for artifact in document["artifacts"]:
        artifact_id = artifact["artifact_id"]
        producer = artifact["producer"]
        producers = [] if producer is None else producer if isinstance(producer, list) else [producer]
        for producer_id in producers:
            require_intent(producer_id, f"artifact {artifact_id!r} producer")
            if producer_id in intents and artifact_id not in intents[producer_id]["outputs"]:
                errors.append(
                    f"artifact {artifact_id!r} names producer {producer_id!r}, but the "
                    "producer does not list it as an output"
                )
        for consumer in artifact["consumers"]:
            require_intent(consumer, f"artifact {artifact_id!r} consumer")
            if consumer in intents and artifact_id not in intents[consumer]["inputs"]:
                errors.append(
                    f"artifact {artifact_id!r} names consumer {consumer!r}, but the "
                    "consumer does not list it as an input"
                )
        if artifact.get("external_system_ref"):
            require_system(artifact["external_system_ref"], f"artifact {artifact_id!r}")

    binding_intents = {item["intent_id"] for item in document["bindings"]}
    missing_bindings = sorted(set(intents) - binding_intents)
    extra_bindings = sorted(binding_intents - set(intents))
    if missing_bindings:
        errors.append(f"service intents without bindings: {missing_bindings}")
    if extra_bindings:
        errors.append(f"bindings for unknown intents: {extra_bindings}")

    for binding in document["bindings"]:
        intent_id = binding["intent_id"]
        require_intent(intent_id, "binding")
        intent = intents.get(intent_id)
        for item in binding["input_bindings"]:
            artifact_id = item["artifact_id"]
            require_artifact(artifact_id, f"binding {intent_id!r} input")
            if intent and artifact_id not in intent["inputs"]:
                errors.append(
                    f"binding {intent_id!r} maps input artifact {artifact_id!r} "
                    "that is not declared by the intent"
                )
        for item in binding["output_bindings"]:
            artifact_id = item["artifact_id"]
            require_artifact(artifact_id, f"binding {intent_id!r} output")
            if intent and artifact_id not in intent["outputs"]:
                errors.append(
                    f"binding {intent_id!r} maps output artifact {artifact_id!r} "
                    "that is not declared by the intent"
                )

    for override in document["policies"]["service_overrides"]:
        require_intent(override["intent_id"], "service policy override")

    gates = [item["gate"] for item in document["validation_expectations"]]
    duplicates = duplicate_values(gates)
    if duplicates:
        errors.append(f"validation_expectations contains duplicate gates: {duplicates}")
    expected_gates = {f"G{index}" for index in range(7)}
    missing_gates = sorted(expected_gates - set(gates))
    if missing_gates:
        errors.append(f"validation_expectations is missing gates: {missing_gates}")

    if errors:
        raise SemanticValidationError(errors)


def validate_path(document_path: Path, schema_path: Path, kind: str) -> None:
    document = load_document(document_path)
    schema = load_schema(schema_path)
    validate_against_schema(document, schema)
    if kind == "service-descriptor":
        validate_service_descriptor_semantics(document)
    elif kind == "serviceflow-ir":
        validate_serviceflow_references(document)
    else:
        raise ValueError(f"Unsupported artifact kind: {kind}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=("service-descriptor", "serviceflow-ir"),
    )
    parser.add_argument("document", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_path(args.document, args.schema, args.kind)
    print(f"Valid {args.kind}: {args.document}")


if __name__ == "__main__":
    main()
