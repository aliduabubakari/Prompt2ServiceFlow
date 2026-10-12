from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from prompt2serviceflow.validators.schema_validation import (
    SemanticValidationError,
    load_document,
    load_schema,
    validate_against_schema,
    validate_service_descriptor_semantics,
    validate_serviceflow_references,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
EXAMPLES = SCHEMAS / "examples"


@pytest.mark.parametrize(
    "schema_name",
    [
        "service_descriptor.schema.json",
        "serviceflow_ir.schema.json",
        "runtime_manifest.schema.json",
        "assertions.schema.json",
        "validation_report.schema.json",
    ],
)
def test_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_http_json_fetcher_descriptor_is_valid() -> None:
    document = load_document(EXAMPLES / "http_json_fetcher.service.yaml")
    schema = load_schema(SCHEMAS / "service_descriptor.schema.json")

    validate_against_schema(document, schema)
    validate_service_descriptor_semantics(document)


@pytest.mark.parametrize(
    "example_name",
    [
        "airvisual.serviceflow.yaml",
        "data_quality_gate.serviceflow.yaml",
    ],
)
def test_serviceflow_examples_are_valid(example_name: str) -> None:
    document = load_document(EXAMPLES / example_name)
    schema = load_schema(SCHEMAS / "serviceflow_ir.schema.json")

    validate_against_schema(document, schema)
    validate_serviceflow_references(document)


def test_service_descriptor_rejects_hidden_gold_label() -> None:
    document = load_document(EXAMPLES / "http_json_fetcher.service.yaml")
    document["benchmark_label"] = "gold"
    schema = load_schema(SCHEMAS / "service_descriptor.schema.json")

    with pytest.raises(SemanticValidationError):
        validate_against_schema(document, schema)


def test_serviceflow_semantics_reject_dangling_intent_reference() -> None:
    document = load_document(EXAMPLES / "airvisual.serviceflow.yaml")
    invalid = copy.deepcopy(document)
    invalid["control_flow"]["edges"][0]["to"] = "missing_intent"

    with pytest.raises(SemanticValidationError, match="unknown intent"):
        validate_serviceflow_references(invalid)


def test_serviceflow_semantics_require_one_binding_per_intent() -> None:
    document = load_document(EXAMPLES / "airvisual.serviceflow.yaml")
    invalid = copy.deepcopy(document)
    invalid["bindings"].pop()

    with pytest.raises(SemanticValidationError, match="without bindings"):
        validate_serviceflow_references(invalid)


def test_serviceflow_semantics_reject_inconsistent_source_step_accounting() -> None:
    document = load_document(EXAMPLES / "airvisual.serviceflow.yaml")
    invalid = copy.deepcopy(document)
    invalid["source_step_accounting"] = [
        {
            "source_step_ref": "get_airvisual_data_hourly",
            "disposition": "service",
            "intent_ids": ["normalize_airvisual_records"],
            "rationale": "Deliberately inconsistent test fixture.",
        }
    ]

    with pytest.raises(
        SemanticValidationError,
        match="does not reference the source step",
    ):
        validate_serviceflow_references(invalid)


def test_serviceflow_semantics_require_service_accounting_to_name_an_intent() -> None:
    document = load_document(EXAMPLES / "airvisual.serviceflow.yaml")
    invalid = copy.deepcopy(document)
    invalid["source_step_accounting"] = [
        {
            "source_step_ref": "get_airvisual_data_hourly",
            "disposition": "service",
            "intent_ids": [],
            "rationale": "Deliberately incomplete test fixture.",
        }
    ]

    with pytest.raises(SemanticValidationError, match="has no intent IDs"):
        validate_serviceflow_references(invalid)


def test_serviceflow_semantics_accept_conditional_artifact_producers() -> None:
    document = load_document(EXAMPLES / "data_quality_gate.serviceflow.yaml")
    conditional = copy.deepcopy(document)
    artifact = next(item for item in conditional["artifacts"] if item["artifact_id"] == "quality_decision")
    artifact["producer"] = ["assess_customer_quality", "load_production_data"]
    load_intent = next(
        item for item in conditional["service_intents"] if item["intent_id"] == "load_production_data"
    )
    load_intent["outputs"].append("quality_decision")

    validate_against_schema(conditional, load_schema(SCHEMAS / "serviceflow_ir.schema.json"))
    validate_serviceflow_references(conditional)
