from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from prompt2serviceflow.catalog.generation_models import (
    CandidateRelation,
    CandidateSet,
    DistractorServiceResponse,
    ProposedContract,
    ProposedDataPort,
    RequiredServiceResponse,
    ReusedService,
    ServiceProposal,
    StepAccounting,
)
from prompt2serviceflow.catalog.generator import (
    PipelineSource,
    RunSettings,
    SUPPLEMENTAL_SERVICE_IDS,
    build_supplemental_registry,
    build_corpus_index,
    build_prompt,
    call_model,
    canonical_candidate_set_id,
    distractor_retry_prompt,
    latest_attempt,
    materialize_descriptor,
    normalize_duplicate_gold_candidates,
    normalize_step_accounting_service_ids,
    potential_duplicate_pairs,
    reject_attempt,
    validate_curated_catalog,
    validate_candidate_sets,
    validate_descriptor,
    validate_step_accounting,
)


def pipeline() -> PipelineSource:
    return PipelineSource(
        manifest={
            "benchmark_id": "main:demo",
            "pipeline_id": "demo",
            "pipeline_name": "Demo",
            "business_domain": "test",
            "execution_model": "Batch",
            "topology": "Linear",
            "information_sufficiency": "high",
        },
        description="A public description for the active demo pipeline.",
        internal_spec={
            "summary": {"purpose": "Fetch and validate a JSON document."},
            "steps": [
                {
                    "step_id": "fetch",
                    "objective": "Fetch JSON",
                    "mechanism": "http",
                    "inputs": [],
                    "outputs": [{"type": "json"}],
                }
            ],
        },
    )


def settings(tmp_path: Path) -> RunSettings:
    return RunSettings(
        run_id="test",
        run_root=tmp_path,
        catalog_version="0.1.0",
        model="gpt-5.5",
        reasoning_effort="medium",
        reasoning_summary="auto",
        verbosity="low",
        max_output_tokens=30000,
        temperature=None,
        timeout_seconds=900,
        store=False,
        splits=("main",),
        owner="Prompt2ServiceFlow",
        created_at="2026-06-13T00:00:00Z",
    )


def proposal(service_id: str = "http_json_fetcher") -> ServiceProposal:
    return ServiceProposal(
        service_id=service_id,
        display_name="HTTP JSON Fetcher",
        category="Extractor",
        capability_summary="Fetch a JSON document from a configured HTTP endpoint.",
        operations=["issue an HTTP GET request", "emit JSON"],
        keywords=["http", "json"],
        limitations=["The mock implementation uses a local fixture."],
        source_step_refs=["fetch"],
        inputs=[],
        outputs=[
            ProposedDataPort(
                name="raw_json",
                description="Raw JSON response.",
                channel="artifact",
                data_type="json",
                media_type="application/json",
                schema_ref=None,
                required=True,
                cardinality="one",
                sensitivity="internal",
            )
        ],
        parameters=[],
        secrets=[],
        contracts=[
            ProposedContract(
                contract_id="valid_json",
                type="semantic",
                applies_to="output",
                target="raw_json",
                description="Output is valid JSON.",
                schema_ref=None,
                expression="is_valid_json(raw_json)",
            )
        ],
        lifecycle_status="active",
        network_access="required",
        allowed_network_targets=["configured endpoint only"],
        secret_access="optional",
        retry_safe=True,
        idempotency="idempotent",
        idempotency_notes="The operation is read-only.",
        default_timeout_seconds=120,
        data_sensitivity=["internal"],
        governance_notes=[],
        rationale="This is a reusable protocol and format-specific extraction capability.",
        ambiguity="explicit",
    )


def test_materialized_proposal_satisfies_service_descriptor_schema(tmp_path: Path) -> None:
    descriptor = materialize_descriptor(proposal(), "main:demo", settings(tmp_path))

    validate_descriptor(descriptor)
    assert descriptor["provenance"]["source_refs"] == ["main:demo#fetch"]
    assert descriptor["invocation"]["template_name"] == "http-json-fetcher-v1"


def test_unknown_contract_target_is_normalized_to_service_scope(tmp_path: Path) -> None:
    value = proposal()
    value.contracts[0].target = "endpoint_and_query_parameters"

    descriptor = materialize_descriptor(value, "main:demo", settings(tmp_path))

    validate_descriptor(descriptor)
    contract = descriptor["contracts"][0]
    assert contract["applies_to"] == "service"
    assert contract["target"] == "http_json_fetcher"
    assert "normalized to service scope" in descriptor["provenance"]["notes"][-1]


def test_prompt_contains_full_active_pipeline_and_compact_corpus_index() -> None:
    item = pipeline()
    prompt = build_prompt("required", item, build_corpus_index([item]), {})

    assert "# Active public description" in prompt
    assert item.description in prompt
    assert '"step_id": "fetch"' in prompt
    assert "# Current registry" in prompt


def test_candidate_set_id_is_globally_namespaced() -> None:
    assert (
        canonical_candidate_set_id(pipeline(), "http_json_fetcher")
        == "main_demo_http_json_fetcher_candidates"
    )


def test_supplemental_registry_contains_bounded_reviewed_pool(tmp_path: Path) -> None:
    source_ids = {
        "csv_tabular_schema_validating_loader",
        "http_json_request_extractor",
        "tabular_dataset_database_loader",
        "postgres_parameterized_sql_executor",
        "email_notification_sender",
    }
    registry = {
        service_id: materialize_descriptor(
            proposal(service_id),
            "main:source",
            settings(tmp_path),
        )
        for service_id in source_ids
    }

    supplemental = build_supplemental_registry(settings(tmp_path), registry)

    assert set(supplemental) == SUPPLEMENTAL_SERVICE_IDS
    assert len(supplemental) == 8
    assert sum(
        descriptor["lifecycle"]["status"] == "deprecated"
        for descriptor in supplemental.values()
    ) == 3
    assert all(
        descriptor["provenance"]["review_status"] == "reviewed"
        for descriptor in supplemental.values()
    )


def test_finalize_audit_requires_curation_report(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run the curate command first"):
        validate_curated_catalog(settings(tmp_path), [pipeline()], {})


def test_required_response_accounts_for_every_step(tmp_path: Path) -> None:
    item = pipeline()
    parsed = RequiredServiceResponse(
        pipeline_id="demo",
        pipeline_summary="Fetch and validate a JSON document.",
        step_accounting=[
            StepAccounting(
                step_id="fetch",
                disposition="service",
                required_service_ids=["http_json_fetcher"],
                rationale="The step is a reusable extraction capability.",
            )
        ],
        reused_services=[
            ReusedService(
                service_id="http_json_fetcher",
                source_step_refs=["fetch"],
                rationale="The existing interface matches.",
            )
        ],
        new_services=[],
        unresolved_requirements=[],
        review_notes=[],
    )
    registry = {
        "http_json_fetcher": materialize_descriptor(
            proposal(), "main:other", settings(tmp_path)
        )
    }

    validate_step_accounting(item, parsed, registry)


def test_unambiguous_final_role_word_mismatch_is_normalized() -> None:
    item = pipeline()
    parsed = RequiredServiceResponse(
        pipeline_id="demo",
        pipeline_summary="Fetch and validate a JSON document.",
        step_accounting=[
            StepAccounting(
                step_id="fetch",
                disposition="service",
                required_service_ids=["http_json_transformer"],
                rationale="The step is a reusable extraction capability.",
            )
        ],
        reused_services=[],
        new_services=[proposal("http_json_fetcher")],
        unresolved_requirements=[],
        review_notes=[],
    )

    normalizations = normalize_step_accounting_service_ids(parsed, {})

    assert parsed.step_accounting[0].required_service_ids == ["http_json_fetcher"]
    assert normalizations == [
        {
            "step_id": "fetch",
            "from_service_id": "http_json_transformer",
            "to_service_id": "http_json_fetcher",
            "reason": "unambiguous_final_role_word_mismatch",
        }
    ]
    validate_step_accounting(item, parsed, {})


def test_ambiguous_final_role_word_mismatch_is_not_normalized() -> None:
    parsed = RequiredServiceResponse(
        pipeline_id="demo",
        pipeline_summary="Fetch and validate a JSON document.",
        step_accounting=[
            StepAccounting(
                step_id="fetch",
                disposition="service",
                required_service_ids=["http_json_processor"],
                rationale="The step is a reusable extraction capability.",
            )
        ],
        reused_services=[],
        new_services=[
            proposal("http_json_fetcher"),
            proposal("http_json_reader"),
        ],
        unresolved_requirements=[],
        review_notes=[],
    )

    normalizations = normalize_step_accounting_service_ids(parsed, {})

    assert normalizations == []
    assert parsed.step_accounting[0].required_service_ids == ["http_json_processor"]


def test_candidate_set_requires_gold_and_known_distractors(tmp_path: Path) -> None:
    registry = {
        "http_json_fetcher": materialize_descriptor(
            proposal(), "main:demo", settings(tmp_path)
        ),
        "generic_rest_requester": materialize_descriptor(
            proposal("generic_rest_requester"), "main:other", settings(tmp_path)
        ),
        "csv_http_downloader": materialize_descriptor(
            proposal("csv_http_downloader"), "main:other", settings(tmp_path)
        ),
    }
    required_mapping = {
        "step_accounting": [
            {
                "step_id": "fetch",
                "disposition": "service",
                "required_service_ids": ["http_json_fetcher"],
                "rationale": "Required.",
            }
        ]
    }
    parsed = DistractorServiceResponse(
        pipeline_id="demo",
        candidate_sets=[
            CandidateSet(
                candidate_set_id="fetch_candidates",
                required_service_id="http_json_fetcher",
                source_step_refs=["fetch"],
                candidates=[
                    CandidateRelation(
                        service_id="http_json_fetcher",
                        label="gold",
                        rationale="Matches protocol and format.",
                    ),
                    CandidateRelation(
                        service_id="generic_rest_requester",
                        label="contract_mismatch",
                        rationale="Does not guarantee the required JSON contract.",
                    ),
                    CandidateRelation(
                        service_id="csv_http_downloader",
                        label="format_mismatch",
                        rationale="Emits CSV rather than JSON.",
                    ),
                ],
            )
        ],
        new_distractor_services=[],
        review_notes=[],
    )

    validate_candidate_sets(parsed, required_mapping, registry)


def test_non_gold_duplicate_of_required_service_is_removed(tmp_path: Path) -> None:
    registry = {
        "http_json_fetcher": materialize_descriptor(
            proposal(), "main:demo", settings(tmp_path)
        ),
        "generic_rest_requester": materialize_descriptor(
            proposal("generic_rest_requester"), "main:other", settings(tmp_path)
        ),
        "csv_http_downloader": materialize_descriptor(
            proposal("csv_http_downloader"), "main:other", settings(tmp_path)
        ),
    }
    required_mapping = {
        "step_accounting": [
            {
                "step_id": "fetch",
                "disposition": "service",
                "required_service_ids": ["http_json_fetcher"],
                "rationale": "Required.",
            }
        ]
    }
    parsed = DistractorServiceResponse(
        pipeline_id="demo",
        candidate_sets=[
            CandidateSet(
                candidate_set_id="fetch_candidates",
                required_service_id="http_json_fetcher",
                source_step_refs=["fetch"],
                candidates=[
                    CandidateRelation(
                        service_id="http_json_fetcher",
                        label="gold",
                        rationale="Matches the required contract.",
                    ),
                    CandidateRelation(
                        service_id="generic_rest_requester",
                        label="contract_mismatch",
                        rationale="Does not guarantee JSON output.",
                    ),
                    CandidateRelation(
                        service_id="csv_http_downloader",
                        label="format_mismatch",
                        rationale="Produces CSV rather than JSON.",
                    ),
                    CandidateRelation(
                        service_id="http_json_fetcher",
                        label="policy_incompatible",
                        rationale="Hypothetical incompatible configuration.",
                    ),
                ],
            )
        ],
        new_distractor_services=[],
        review_notes=[],
    )

    normalizations = normalize_duplicate_gold_candidates(parsed)

    assert [item.service_id for item in parsed.candidate_sets[0].candidates] == [
        "http_json_fetcher",
        "generic_rest_requester",
        "csv_http_downloader",
    ]
    assert normalizations == [
        {
            "candidate_set_id": "fetch_candidates",
            "service_id": "http_json_fetcher",
            "removed_label": "policy_incompatible",
            "reason": "duplicate_copy_of_required_gold_service",
        }
    ]
    validate_candidate_sets(parsed, required_mapping, registry)


def test_duplicate_gold_copy_is_removed(tmp_path: Path) -> None:
    registry = {
        "http_json_fetcher": materialize_descriptor(
            proposal(), "main:demo", settings(tmp_path)
        ),
        "generic_rest_requester": materialize_descriptor(
            proposal("generic_rest_requester"), "main:other", settings(tmp_path)
        ),
        "csv_http_downloader": materialize_descriptor(
            proposal("csv_http_downloader"), "main:other", settings(tmp_path)
        ),
    }
    required_mapping = {
        "step_accounting": [
            {
                "step_id": "fetch",
                "required_service_ids": ["http_json_fetcher"],
            }
        ]
    }
    parsed = DistractorServiceResponse(
        pipeline_id="demo",
        candidate_sets=[
            CandidateSet(
                candidate_set_id="fetch_candidates",
                required_service_id="http_json_fetcher",
                source_step_refs=["fetch"],
                candidates=[
                    CandidateRelation(
                        service_id="http_json_fetcher",
                        label="gold",
                        rationale="Matches the required contract.",
                    ),
                    CandidateRelation(
                        service_id="generic_rest_requester",
                        label="contract_mismatch",
                        rationale="Does not guarantee JSON output.",
                    ),
                    CandidateRelation(
                        service_id="csv_http_downloader",
                        label="format_mismatch",
                        rationale="Produces CSV rather than JSON.",
                    ),
                    CandidateRelation(
                        service_id="http_json_fetcher",
                        label="gold",
                        rationale="Repeated gold relation.",
                    ),
                ],
            )
        ],
        new_distractor_services=[],
        review_notes=[],
    )

    normalizations = normalize_duplicate_gold_candidates(parsed)

    assert len(parsed.candidate_sets[0].candidates) == 3
    assert normalizations[0]["removed_label"] == "gold"
    validate_candidate_sets(parsed, required_mapping, registry)


def test_rejected_attempt_is_skipped_and_retry_prompt_lists_required_ids(
    tmp_path: Path,
) -> None:
    item = pipeline()
    current = (
        tmp_path
        / "attempts"
        / "distractors"
        / f"{item.benchmark_id.replace(':', '__')}__01.json"
    )
    current.parent.mkdir(parents=True)
    current.write_text('{"parsed": {}}\n', encoding="utf-8")
    error = ValueError("Candidate-set coverage mismatch")

    reject_attempt(current, error)

    assert latest_attempt(settings(tmp_path), "distractors", item) is None
    retry = distractor_retry_prompt(
        item,
        {
            "step_accounting": [
                {
                    "step_id": "fetch",
                    "required_service_ids": ["http_json_fetcher"],
                }
            ]
        },
        {
            "http_json_fetcher": materialize_descriptor(
                proposal(), "main:demo", settings(tmp_path)
            ),
            "csv_http_downloader": materialize_descriptor(
                proposal("csv_http_downloader"), "main:other", settings(tmp_path)
            ),
        },
        error,
    )
    assert "Candidate-set coverage mismatch" in retry
    assert '"http_json_fetcher"' in retry
    assert '"required_candidate_set_count": 1' in retry
    assert "# Compact candidate-service index" in retry
    assert len(retry) < 30_000


def test_duplicate_report_flags_highly_similar_capabilities(tmp_path: Path) -> None:
    left = materialize_descriptor(proposal(), "main:demo", settings(tmp_path))
    right = materialize_descriptor(
        proposal("http_json_reader"), "main:other", settings(tmp_path)
    )

    pairs = potential_duplicate_pairs(
        {"http_json_fetcher": left, "http_json_reader": right},
        threshold=0.4,
    )

    assert pairs


def test_sdk_request_uses_responses_api_controls(tmp_path: Path) -> None:
    parsed = RequiredServiceResponse(
        pipeline_id="demo",
        pipeline_summary="Fetch a JSON document from an HTTP endpoint.",
        step_accounting=[
            StepAccounting(
                step_id="fetch",
                disposition="service",
                required_service_ids=["http_json_fetcher"],
                rationale="The step is a reusable extraction capability.",
            )
        ],
        reused_services=[],
        new_services=[proposal()],
        unresolved_requirements=[],
        review_notes=[],
    )
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "completed_at": 2,
                "error": None,
                "incomplete_details": None,
                "instructions": None,
                "max_output_tokens": 30000,
                "model": "gpt-5.5",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": parsed.model_dump_json(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "parallel_tool_calls": True,
                "previous_response_id": None,
                "reasoning": {"effort": "medium", "summary": None},
                "store": False,
                "temperature": 1.0,
                "text": {"format": {"type": "text"}, "verbosity": "low"},
                "tool_choice": "auto",
                "tools": [],
                "top_p": 1.0,
                "truncation": "disabled",
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 20,
                    "output_tokens_details": {"reasoning_tokens": 5},
                    "total_tokens": 30,
                },
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(api_key="test", http_client=http_client)

    response, output = call_model(
        client,
        settings(tmp_path),
        "Analyze the active pipeline.",
        RequiredServiceResponse,
        pipeline(),
        "required",
    )

    assert response.id == "resp_test"
    assert output.pipeline_id == "demo"
    assert captured["path"] == "/v1/responses"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["max_output_tokens"] == 30000
    assert "temperature" not in body
    assert body["reasoning"] == {"effort": "medium", "summary": "auto"}
    assert body["text"]["verbosity"] == "low"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["prompt_cache_key"] == "prompt2serviceflow-catalog-required-main"
    assert body["prompt_cache_retention"] == "24h"
