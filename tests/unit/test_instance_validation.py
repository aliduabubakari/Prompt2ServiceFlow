from __future__ import annotations

from copy import deepcopy

from prompt2serviceflow.validators.instance_validation import (
    CONFIGMAP_DATA_LIMIT_BYTES,
    _configmap_data_size_bytes,
    _json_path,
    _validate_candidate_grounding,
    _validate_contract_closure,
)


def fixture_documents() -> tuple[dict, dict, dict, dict]:
    serviceflow = {
        "service_intents": [
            {"intent_id": "extract", "source_step_refs": ["source_extract"]},
            {"intent_id": "load", "source_step_refs": ["source_load"]},
        ],
        "bindings": [
            {
                "intent_id": "extract",
                "service_id": "extractor",
                "service_version": "1.0.0",
            },
            {
                "intent_id": "load",
                "service_id": "loader",
                "service_version": "1.0.0",
            },
        ],
    }
    candidates = {
        "candidate_sets": [
            {
                "candidate_set_id": "main_demo_extractor_candidates",
                "source_step_refs": ["source_extract"],
                "service_ids": ["extractor", "alternate_a", "alternate_b"],
            },
            {
                "candidate_set_id": "main_demo_loader_candidates",
                "source_step_refs": ["source_load"],
                "service_ids": ["loader", "alternate_a", "alternate_b"],
            },
        ]
    }
    labels = {
        "candidate_sets": [
            {
                "candidate_set_id": "main_demo_extractor_candidates",
                "required_service_id": "extractor",
                "labels": {
                    "extractor": "gold",
                    "alternate_a": "semantic_mismatch",
                    "alternate_b": "contract_mismatch",
                },
            },
            {
                "candidate_set_id": "main_demo_loader_candidates",
                "required_service_id": "loader",
                "labels": {
                    "loader": "gold",
                    "alternate_a": "semantic_mismatch",
                    "alternate_b": "contract_mismatch",
                },
            },
        ]
    }
    catalog = {
        (service_id, "1.0.0"): {"lifecycle": {"status": "active"}}
        for service_id in ["extractor", "loader", "alternate_a", "alternate_b"]
    }
    return serviceflow, candidates, labels, catalog


def test_candidate_grounding_accepts_complete_service_coverage() -> None:
    serviceflow, candidates, labels, catalog = fixture_documents()

    assert _validate_candidate_grounding(serviceflow, candidates, labels, catalog) == []


def test_candidate_grounding_rejects_bound_service_without_gold_set() -> None:
    serviceflow, candidates, labels, catalog = fixture_documents()
    candidates["candidate_sets"].pop()
    labels["candidate_sets"].pop()

    errors = _validate_candidate_grounding(serviceflow, candidates, labels, catalog)

    assert "bound services without gold candidate sets: ['loader']" in errors


def test_candidate_grounding_rejects_cross_service_source_refs() -> None:
    serviceflow, candidates, labels, catalog = fixture_documents()
    broken_candidates = deepcopy(candidates)
    broken_candidates["candidate_sets"][0]["source_step_refs"].append("source_load")

    errors = _validate_candidate_grounding(
        serviceflow,
        broken_candidates,
        labels,
        catalog,
    )

    assert any("source-step coverage does not match" in error for error in errors)


def test_contract_closure_accepts_cardinality_many_input_bindings() -> None:
    serviceflow = {
        "artifacts": [
            {"artifact_id": "first", "data_type": "csv"},
            {"artifact_id": "second", "data_type": "csv"},
            {"artifact_id": "output", "data_type": "csv"},
        ],
        "service_intents": [
            {
                "intent_id": "aggregate",
                "inputs": ["first", "second"],
                "outputs": ["output"],
                "required_policy_properties": {"network_access": "forbidden"},
            }
        ],
        "bindings": [
            {
                "intent_id": "aggregate",
                "service_id": "aggregator",
                "service_version": "1.0.0",
                "input_bindings": [
                    {"port": "inputs", "artifact_id": "first"},
                    {"port": "inputs", "artifact_id": "second"},
                ],
                "output_bindings": [{"port": "output", "artifact_id": "output"}],
                "parameter_bindings": {},
                "secret_bindings": [],
            }
        ],
    }
    catalog = {
        ("aggregator", "1.0.0"): {
            "interface": {
                "inputs": [
                    {"name": "inputs", "data_type": "csv", "required": True, "cardinality": "many"}
                ],
                "outputs": [
                    {"name": "output", "data_type": "csv", "required": True, "cardinality": "one"}
                ],
                "parameters": [],
                "secrets": [],
            },
            "policies": {"network_access": "forbidden"},
        }
    }

    assert _validate_contract_closure(serviceflow, catalog) == []


def test_configmap_payload_size_counts_utf8_keys_and_values() -> None:
    resource = {"data": {"scripts.py": "print('hello')", "ø": "å"}}

    assert _configmap_data_size_bytes(resource) == len(
        "scripts.pyprint('hello')øå".encode("utf-8")
    )
    assert _configmap_data_size_bytes(resource) < CONFIGMAP_DATA_LIMIT_BYTES


def test_configmap_payload_size_counts_binary_data() -> None:
    resource = {"binaryData": {"fixture-0000": "AAEC"}}

    assert _configmap_data_size_bytes(resource) == len("fixture-0000".encode()) + 3


def test_json_path_supports_simple_array_filter() -> None:
    document = {"rows": [{"user_id": "allowed"}, {"user_id": "revoked"}]}

    assert _json_path(document, "rows[?(@.user_id=='revoked')]") == [
        {"user_id": "revoked"}
    ]
