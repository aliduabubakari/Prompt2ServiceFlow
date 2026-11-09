"""Generate and assemble a service catalog with one GPT request per pipeline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml
from dotenv import load_dotenv
from jsonschema import Draft202012Validator, FormatChecker
from openai import OpenAI
from pydantic import BaseModel
from pydantic_core import ValidationError as PydanticValidationError

from prompt2serviceflow.catalog.generation_models import (
    CandidateRelation,
    DistractorServiceResponse,
    RequiredServiceResponse,
    ServiceProposal,
)
from prompt2serviceflow.validators.schema_validation import (
    validate_service_descriptor_semantics,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "catalog_generation.yaml"
SERVICE_SCHEMA = ROOT / "schemas" / "service_descriptor.schema.json"

SUPPLEMENTAL_SERVICE_IDS = {
    "legacy_csv_schema_validator",
    "legacy_http_json_extractor",
    "legacy_database_table_loader",
    "open_network_http_json_requester",
    "unreviewed_postgres_sql_executor",
    "unrestricted_email_notification_sender",
    "reviewed_python_udf_transformer",
    "reviewed_domain_adapter",
}

SYSTEM_INSTRUCTIONS = """\
You are the catalogue architect for ServiceComposeBench-ETL.

Your job is to identify reusable, closed-world service capabilities for
contract-grounded Argo Workflow compositions. Produce catalogue services, not
pipeline-specific tasks. Prefer a generic service that can be configured for
several pipelines over one service named after a source pipeline, company, or
dataset.

Success criteria:
- account for every source step;
- keep schedules, dependency edges, branches, fan-out/fan-in, retries, and
  workflow failure hooks outside the service catalogue;
- represent sensors and readiness checks as services when they are reusable
  invokable capabilities;
- split a source step only when it contains independently meaningful reusable
  effects or artifact boundaries;
- reuse an existing service whenever its capability, interface, contracts, and
  policies satisfy the requirement;
- create a new service only when reuse would lose a material contract;
- use snake_case stable IDs and the supplied taxonomy;
- make interfaces and contracts concrete enough to support deterministic Argo
  binding and mock execution;
- do not include gold, correct, wrong, or distractor labels in service
  descriptors;
- do not invent credentials, image digests, or infrastructure availability;
- expose uncertainty honestly through the ambiguity field and review notes.

Operational invocation boilerplate, runtime compatibility, provenance
timestamps, and image references are filled deterministically by the local
catalogue builder. Focus on capability semantics, interfaces, contracts, and
policy requirements.
"""

REQUIRED_TASK = """\
Analyze exactly one active pipeline. Map every source step to one of:
service, orchestration, noop, or unresolvable.

Use existing registry services where they satisfy the full requirement.
Propose new reusable required services only for genuine gaps. Required
services should normally be active, not deprecated. A loader, publisher, or
sensor must still expose a useful status or decision output so downstream
workflow validation can observe its effect.

Return the structured required-service response. Stop after accounting for the
active pipeline; do not analyze another pipeline.
"""

DISTRACTOR_TASK = """\
Analyze exactly one active pipeline using its reviewed required-service
mapping and the complete required registry.

For each required service used by this pipeline, produce one candidate set
containing:
- exactly one gold relation to the required service;
- two to five plausible alternatives;
- alternatives that overlap in names or capability but fail a meaningful
  format, target-system, lifecycle, output, policy, or contract requirement.

Return exactly one candidate set for every distinct required service ID in the
reviewed mapping. Never return a partial response, duplicate a service within
a candidate set, or describe an invalid draft in review notes.

Reuse an existing registry service as an alternative when plausible. Propose a
new distractor service only when the registry lacks a realistic alternative.
Do not put relationship labels inside service descriptors. Stop after the
active pipeline.
"""


@dataclass(frozen=True)
class PipelineSource:
    manifest: dict[str, Any]
    description: str
    internal_spec: dict[str, Any]

    @property
    def benchmark_id(self) -> str:
        return str(self.manifest["benchmark_id"])

    @property
    def pipeline_id(self) -> str:
        return str(self.manifest["pipeline_id"])


@dataclass(frozen=True)
class RunSettings:
    run_id: str
    run_root: Path
    catalog_version: str
    model: str
    reasoning_effort: str
    reasoning_summary: str
    verbosity: str
    max_output_tokens: int
    temperature: float | None
    timeout_seconds: float
    store: bool
    splits: tuple[str, ...]
    owner: str
    created_at: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_settings(
    config_path: Path,
    run_id: str | None,
    split_override: list[str] | None = None,
) -> RunSettings:
    config = load_config(config_path)
    generation = config["generation"]
    catalog = config["catalog"]
    effective_run_id = run_id or generation["run_id"]
    run_root = ROOT / generation["run_root"] / effective_run_id
    state_path = run_root / "run.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        created_at = state["created_at"]
    else:
        created_at = datetime.now(timezone.utc).isoformat()
    return RunSettings(
        run_id=effective_run_id,
        run_root=run_root,
        catalog_version=str(catalog["version"]),
        model=str(generation["model"]),
        reasoning_effort=str(generation["reasoning_effort"]),
        reasoning_summary=str(generation["reasoning_summary"]),
        verbosity=str(generation["verbosity"]),
        max_output_tokens=int(generation["max_output_tokens"]),
        temperature=(
            float(generation["temperature"])
            if generation.get("temperature") is not None
            else None
        ),
        timeout_seconds=float(generation["timeout_seconds"]),
        store=bool(generation["store"]),
        splits=tuple(split_override or generation["splits"]),
        owner=str(catalog["owner"]),
        created_at=created_at,
    )


def initialize_run(settings: RunSettings, config_path: Path) -> None:
    settings.run_root.mkdir(parents=True, exist_ok=True)
    state_path = settings.run_root / "run.json"
    state = {
        "run_id": settings.run_id,
        "created_at": settings.created_at,
        "catalog_version": settings.catalog_version,
        "model": settings.model,
        "reasoning_effort": settings.reasoning_effort,
        "reasoning_summary": settings.reasoning_summary,
        "verbosity": settings.verbosity,
        "max_output_tokens": settings.max_output_tokens,
        "temperature": settings.temperature,
        "store": settings.store,
        "splits": list(settings.splits),
        "config_path": str(config_path.relative_to(ROOT)),
        "config_sha256": sha256_file(config_path),
    }
    if state_path.exists():
        existing = json.loads(state_path.read_text(encoding="utf-8"))
        if not any((settings.run_root / "responses").glob("*/*.json")):
            # A run that has produced no accepted responses may safely adopt
            # corrected API controls without requiring a new run ID.
            existing = state
            write_json(state_path, existing)
        else:
            mutable_controls = {
                "reasoning_effort",
                "reasoning_summary",
                "verbosity",
                "max_output_tokens",
                "temperature",
            }
            changed = {
                key
                for key in state
                if key != "config_sha256" and existing.get(key) != state[key]
            }
            if changed and changed <= mutable_controls:
                revisions = existing.get("settings_revisions", [])
                revisions.append(
                    {
                        "changed_at": datetime.now(timezone.utc).isoformat(),
                        "changed_fields": sorted(changed),
                        "previous": {key: existing.get(key) for key in sorted(changed)},
                    }
                )
                existing = {**state, "settings_revisions": revisions}
                write_json(state_path, existing)
        comparable = {key: value for key, value in state.items() if key != "config_sha256"}
        old_comparable = {key: existing.get(key) for key in comparable}
        if comparable != old_comparable:
            raise ValueError(
                f"Run settings differ from existing state in {state_path}; use a new run ID."
            )
    else:
        write_json(state_path, state)


def load_pipelines(splits: Iterable[str]) -> list[PipelineSource]:
    selected = set(splits)
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pipelines = []
    for row in rows:
        if row["split"] not in selected:
            continue
        description = (ROOT / "benchmark" / row["description_path"]).read_text(encoding="utf-8")
        spec = json.loads(
            (ROOT / "benchmark" / row["internal_spec_path"]).read_text(encoding="utf-8")
        )
        pipelines.append(PipelineSource(row, description, spec))
    return pipelines


def build_corpus_index(pipelines: list[PipelineSource]) -> list[dict[str, Any]]:
    return [
        {
            "benchmark_id": item.benchmark_id,
            "pipeline_id": item.pipeline_id,
            "name": item.manifest["pipeline_name"],
            "domain": item.manifest["business_domain"],
            "execution_model": item.manifest["execution_model"],
            "topology": item.manifest["topology"],
            "information_sufficiency": item.manifest["information_sufficiency"],
            "purpose": item.internal_spec.get("summary", {}).get("purpose"),
            "steps": [
                {
                    "step_id": step.get("step_id"),
                    "objective": step.get("objective"),
                    "mechanism": step.get("mechanism"),
                    "input_types": sorted(
                        {
                            str(value.get("type"))
                            for value in step.get("inputs", [])
                            if value.get("type")
                        }
                    ),
                    "output_types": sorted(
                        {
                            str(value.get("type"))
                            for value in step.get("outputs", [])
                            if value.get("type")
                        }
                    ),
                }
                for step in item.internal_spec.get("steps", [])
            ],
        }
        for item in pipelines
    ]


def descriptor_summary(descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_id": descriptor["service_id"],
        "version": descriptor["version"],
        "category": descriptor["category"],
        "capability": descriptor["capability"],
        "inputs": descriptor["interface"]["inputs"],
        "outputs": descriptor["interface"]["outputs"],
        "parameters": descriptor["interface"]["parameters"],
        "contracts": descriptor["contracts"],
        "policies": descriptor["policies"],
        "lifecycle": descriptor["lifecycle"],
    }


def compact_descriptor_summary(descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_id": descriptor["service_id"],
        "category": descriptor["category"],
        "summary": descriptor["capability"]["summary"],
        "keywords": descriptor["capability"]["keywords"],
        "limitations": descriptor["capability"]["limitations"],
        "inputs": [
            {
                "name": item["name"],
                "data_type": item["data_type"],
                "media_type": item.get("media_type"),
                "schema_ref": item.get("schema_ref"),
                "sensitivity": item["sensitivity"],
            }
            for item in descriptor["interface"]["inputs"]
        ],
        "outputs": [
            {
                "name": item["name"],
                "data_type": item["data_type"],
                "media_type": item.get("media_type"),
                "schema_ref": item.get("schema_ref"),
                "sensitivity": item["sensitivity"],
            }
            for item in descriptor["interface"]["outputs"]
        ],
        "lifecycle_status": descriptor["lifecycle"]["status"],
        "network_access": descriptor["policies"]["network_access"],
        "secret_access": descriptor["policies"]["secret_access"],
    }


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    registry = {}
    for descriptor_path in sorted(path.glob("*.yaml")):
        descriptor = yaml.safe_load(descriptor_path.read_text(encoding="utf-8"))
        registry[descriptor["service_id"]] = descriptor
    return registry


def build_prompt(
    phase: Literal["required", "distractors"],
    pipeline: PipelineSource,
    corpus_index: list[dict[str, Any]],
    registry: dict[str, dict[str, Any]],
    required_mapping: dict[str, Any] | None = None,
) -> str:
    sections = [
        "# Task",
        REQUIRED_TASK if phase == "required" else DISTRACTOR_TASK,
        "# Corpus-wide index",
        json.dumps(corpus_index, indent=2, sort_keys=True),
        "# Current registry",
        json.dumps(
            [descriptor_summary(value) for _, value in sorted(registry.items())],
            indent=2,
            sort_keys=True,
        ),
    ]
    if required_mapping is not None:
        sections.extend(
            [
                "# Reviewed required-service mapping for the active pipeline",
                json.dumps(required_mapping, indent=2, sort_keys=True),
            ]
        )
    sections.extend(
        [
            "# Active pipeline manifest",
            json.dumps(pipeline.manifest, indent=2, sort_keys=True),
            "# Active public description",
            pipeline.description,
            "# Active internal companion specification",
            json.dumps(pipeline.internal_spec, indent=2, sort_keys=True),
        ]
    )
    return "\n\n".join(sections)


def optional_field(value: Any, name: str, target: dict[str, Any]) -> None:
    if value is not None and value != []:
        target[name] = value


def materialize_descriptor(
    proposal: ServiceProposal,
    benchmark_id: str,
    settings: RunSettings,
) -> dict[str, Any]:
    inputs = []
    outputs = []
    for source, target in ((proposal.inputs, inputs), (proposal.outputs, outputs)):
        for port in source:
            value = port.model_dump(exclude_none=True)
            target.append(value)

    parameters = []
    for parameter in proposal.parameters:
        value = {
            "name": parameter.name,
            "description": parameter.description,
            "type": parameter.type,
            "required": parameter.required,
        }
        optional_field(parameter.enum_values, "enum", value)
        optional_field(parameter.pattern, "pattern", value)
        optional_field(parameter.minimum, "minimum", value)
        optional_field(parameter.maximum, "maximum", value)
        parameters.append(value)

    target_names = {
        proposal.service_id,
        *(item.name for item in proposal.inputs),
        *(item.name for item in proposal.outputs),
        *(item.name for item in proposal.parameters),
    }
    contract_normalizations = []
    contracts = []
    for contract in proposal.contracts:
        value = contract.model_dump(exclude_none=True)
        if value["target"] not in target_names:
            contract_normalizations.append(
                f"Contract {value['contract_id']} target {value['target']!r} "
                "was normalized to service scope."
            )
            value["applies_to"] = "service"
            value["target"] = proposal.service_id
        contracts.append(value)
    secrets = [secret.model_dump(exclude_none=True) for secret in proposal.secrets]
    slug = proposal.service_id.replace("_", "-")
    source_refs = sorted(
        {f"{benchmark_id}#{step_id}" for step_id in proposal.source_step_refs}
    )

    policies: dict[str, Any] = {
        "network_access": proposal.network_access,
        "allowed_network_targets": proposal.allowed_network_targets,
        "secret_access": proposal.secret_access,
        "retry_safe": proposal.retry_safe,
        "idempotency": proposal.idempotency,
        "data_sensitivity": proposal.data_sensitivity,
        "resources": {"cpu": "250m", "memory": "256Mi", "gpu": 0},
        "governance_notes": proposal.governance_notes,
    }
    optional_field(proposal.idempotency_notes, "idempotency_notes", policies)
    optional_field(proposal.default_timeout_seconds, "default_timeout_seconds", policies)

    return {
        "schema_version": "0.1.0",
        "service_id": proposal.service_id,
        "version": "1.0.0",
        "display_name": proposal.display_name,
        "category": proposal.category,
        "capability": {
            "summary": proposal.capability_summary,
            "operations": proposal.operations,
            "keywords": proposal.keywords,
            "limitations": proposal.limitations,
        },
        "lifecycle": {"status": proposal.lifecycle_status},
        "interface": {
            "inputs": inputs,
            "outputs": outputs,
            "parameters": parameters,
            "secrets": secrets,
        },
        "contracts": contracts,
        "invocation": {
            "type": "argo_workflow_template",
            "template_name": f"{slug}-v1",
            "template_entrypoint": "main",
            "image": "prompt2serviceflow/runtime:0.1.0",
            "command": [
                "python",
                "-m",
                f"prompt2serviceflow_services.{proposal.service_id}",
            ],
            "implementation_ref": f"services/implementations/{proposal.service_id}",
            "mock_supported": True,
        },
        "policies": policies,
        "compatibility": {
            "runtime": {
                "target": "argo-workflows",
                "minimum_version": "3.5.0",
            },
            "supported_architectures": ["amd64", "arm64"],
            "incompatible_services": [],
        },
        "provenance": {
            "origin": "generated",
            "owner": settings.owner,
            "created_at": settings.created_at,
            "review_status": "candidate",
            "source_refs": source_refs,
            "notes": [
                f"Generated by {settings.model} during run {settings.run_id}.",
                f"Rationale: {proposal.rationale}",
                f"Evidence status: {proposal.ambiguity}.",
                *contract_normalizations,
            ],
        },
    }


def validate_descriptor(descriptor: dict[str, Any]) -> None:
    schema = json.loads(SERVICE_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(descriptor), key=lambda error: list(error.path))
    if errors:
        messages = [f"{list(error.path)}: {error.message}" for error in errors]
        raise ValueError("Invalid generated descriptor:\n" + "\n".join(messages))
    validate_service_descriptor_semantics(descriptor)


def append_source_refs(
    descriptor: dict[str, Any],
    benchmark_id: str,
    step_refs: Iterable[str],
) -> None:
    refs = set(descriptor["provenance"]["source_refs"])
    refs.update(f"{benchmark_id}#{step_id}" for step_id in step_refs)
    descriptor["provenance"]["source_refs"] = sorted(refs)


def response_metadata(response: Any, parsed: BaseModel, prompt: str) -> dict[str, Any]:
    usage = response.usage.model_dump(mode="json") if response.usage else None
    return {
        "response_id": response.id,
        "status": response.status,
        "model": response.model,
        "incomplete_details": (
            response.incomplete_details.model_dump(mode="json")
            if response.incomplete_details
            else None
        ),
        "usage": usage,
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "parsed": parsed.model_dump(mode="json"),
    }


def write_attempt(
    settings: RunSettings,
    phase: str,
    pipeline: PipelineSource,
    metadata: dict[str, Any],
) -> None:
    attempt_root = settings.run_root / "attempts" / phase
    existing = list(attempt_root.glob(f"{pipeline.benchmark_id.replace(':', '__')}__*.json"))
    path = attempt_root / (
        f"{pipeline.benchmark_id.replace(':', '__')}__{len(existing) + 1:02d}.json"
    )
    write_json(path, metadata)


def call_model(
    client: OpenAI,
    settings: RunSettings,
    prompt: str,
    output_model: type[BaseModel],
    pipeline: PipelineSource,
    phase: str,
) -> tuple[Any, BaseModel]:
    request: dict[str, Any] = {
        "model": settings.model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "text_format": output_model,
        "text": {"verbosity": settings.verbosity},
        "reasoning": {
            "effort": settings.reasoning_effort,
            "summary": settings.reasoning_summary,
        },
        "max_output_tokens": settings.max_output_tokens,
        "store": settings.store,
        "truncation": "disabled",
        "metadata": {
            "run_id": settings.run_id,
            "phase": phase,
            "pipeline_id": pipeline.pipeline_id,
        },
        "extra_body": {
            "prompt_cache_key": (
                f"prompt2serviceflow-catalog-{phase}-{'-'.join(settings.splits)}"
            ),
            "prompt_cache_retention": "24h",
        },
        "timeout": settings.timeout_seconds,
    }
    if settings.temperature is not None:
        request["temperature"] = settings.temperature

    try:
        response = client.responses.parse(**request)
    except PydanticValidationError as exc:
        likely_truncated = "EOF while parsing" in str(exc)
        diagnosis = (
            f"The structured JSON was truncated at max_output_tokens="
            f"{settings.max_output_tokens}. This limit includes reasoning and "
            "visible output tokens."
            if likely_truncated
            else "The returned JSON did not satisfy the structured-output schema."
        )
        raise RuntimeError(
            f"{diagnosis} Pipeline={pipeline.benchmark_id}; phase={phase}. "
            "Increase max_output_tokens or reduce reasoning_effort before retrying."
        ) from exc
    if response.status != "completed":
        raise RuntimeError(
            f"Response {response.id} ended with status {response.status}: "
            f"{response.incomplete_details}"
        )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError(f"Response {response.id} did not contain parsed output")
    if parsed.pipeline_id != pipeline.pipeline_id:
        raise ValueError(
            f"Response pipeline_id {parsed.pipeline_id!r} does not match "
            f"{pipeline.pipeline_id!r}"
        )
    return response, parsed


def selected_pipelines(
    pipelines: list[PipelineSource],
    pipeline_ids: list[str],
    limit: int | None,
) -> list[PipelineSource]:
    if pipeline_ids:
        requested = set(pipeline_ids)
        pipelines = [
            item
            for item in pipelines
            if item.pipeline_id in requested or item.benchmark_id in requested
        ]
        found = {item.pipeline_id for item in pipelines} | {
            item.benchmark_id for item in pipelines
        }
        missing = sorted(requested - found)
        if missing:
            raise ValueError(f"Unknown selected pipelines: {missing}")
    return pipelines[:limit] if limit is not None else pipelines


def validate_step_accounting(
    pipeline: PipelineSource,
    parsed: RequiredServiceResponse,
    registry: dict[str, dict[str, Any]],
) -> None:
    expected_steps = {
        str(step["step_id"]) for step in pipeline.internal_spec.get("steps", [])
    }
    accounted = [item.step_id for item in parsed.step_accounting]
    if set(accounted) != expected_steps or len(accounted) != len(set(accounted)):
        raise ValueError(
            f"Step accounting mismatch for {pipeline.pipeline_id}: "
            f"expected={sorted(expected_steps)}, received={sorted(accounted)}"
        )
    new_ids = {item.service_id for item in parsed.new_services}
    reused_ids = {item.service_id for item in parsed.reused_services}
    unknown_reuse = sorted(reused_ids - set(registry))
    if unknown_reuse:
        raise ValueError(f"Response reuses unknown services: {unknown_reuse}")
    duplicate_new = sorted(new_ids & set(registry))
    if duplicate_new:
        raise ValueError(f"Response proposes existing IDs as new: {duplicate_new}")
    duplicate_ids = sorted(new_ids & reused_ids)
    if duplicate_ids:
        raise ValueError(f"Services cannot be both new and reused: {duplicate_ids}")
    mapped_ids = new_ids | reused_ids
    referenced = {
        service_id
        for item in parsed.step_accounting
        for service_id in item.required_service_ids
    }
    unknown_mapping = sorted(referenced - mapped_ids)
    if unknown_mapping:
        raise ValueError(f"Step accounting references undeclared services: {unknown_mapping}")


def normalize_step_accounting_service_ids(
    parsed: RequiredServiceResponse,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Repair an unambiguous final-role-word mismatch in a declared service ID."""
    declared_ids = {
        *(item.service_id for item in parsed.new_services),
        *(item.service_id for item in parsed.reused_services),
    }
    known_ids = declared_ids | set(registry)
    referenced_ids = {
        service_id
        for item in parsed.step_accounting
        for service_id in item.required_service_ids
    }
    aliases: dict[str, str] = {}
    for unknown_id in sorted(referenced_ids - known_ids):
        unknown_parts = unknown_id.split("_")
        candidates = [
            service_id
            for service_id in declared_ids
            if service_id != unknown_id
            and len(service_id.split("_")) == len(unknown_parts)
            and service_id.split("_")[:-1] == unknown_parts[:-1]
        ]
        if len(candidates) == 1:
            aliases[unknown_id] = candidates[0]

    normalizations = []
    for item in parsed.step_accounting:
        corrected = []
        for service_id in item.required_service_ids:
            replacement = aliases.get(service_id, service_id)
            corrected.append(replacement)
            if replacement != service_id:
                normalizations.append(
                    {
                        "step_id": item.step_id,
                        "from_service_id": service_id,
                        "to_service_id": replacement,
                        "reason": "unambiguous_final_role_word_mismatch",
                    }
                )
        item.required_service_ids = corrected
    return normalizations


def accept_required_response(
    settings: RunSettings,
    pipeline: PipelineSource,
    parsed: RequiredServiceResponse,
    metadata: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    registry_path: Path,
    output_file: Path,
) -> None:
    normalizations = normalize_step_accounting_service_ids(parsed, registry)
    validate_step_accounting(pipeline, parsed, registry)
    if normalizations:
        metadata["parsed"] = parsed.model_dump(mode="json")
        metadata.setdefault("normalizations", []).extend(normalizations)
    descriptors = []
    for proposal in parsed.new_services:
        descriptor = materialize_descriptor(proposal, pipeline.benchmark_id, settings)
        validate_descriptor(descriptor)
        descriptors.append(descriptor)
    for reuse in parsed.reused_services:
        append_source_refs(
            registry[reuse.service_id],
            pipeline.benchmark_id,
            reuse.source_step_refs,
        )
        validate_descriptor(registry[reuse.service_id])

    for descriptor in descriptors:
        registry[descriptor["service_id"]] = descriptor
    for service_id, descriptor in sorted(registry.items()):
        write_yaml(registry_path / f"{service_id}.yaml", descriptor)
    write_json(output_file, metadata)
    print(
        f"completed required response: {pipeline.benchmark_id} "
        f"({len(descriptors)} new, {len(parsed.reused_services)} reused)"
    )


def latest_attempt(
    settings: RunSettings,
    phase: str,
    pipeline: PipelineSource,
) -> Path | None:
    paths = sorted(
        (settings.run_root / "attempts" / phase).glob(
            f"{pipeline.benchmark_id.replace(':', '__')}__*.json"
        )
    )
    for path in reversed(paths):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if "local_rejection" not in metadata:
            return path
    return None


def reject_attempt(path: Path, error: Exception) -> None:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["local_rejection"] = {
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    write_json(path, metadata)


def distractor_retry_prompt(
    pipeline: PipelineSource,
    required_mapping: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    error: Exception,
) -> str:
    required_ids = sorted(
        {
            service_id
            for item in required_mapping["step_accounting"]
            for service_id in item["required_service_ids"]
        }
    )
    correction = {
        "local_validation_error": str(error),
        "required_service_ids": required_ids,
        "required_candidate_set_count": len(required_ids),
        "instructions": [
            "Return a complete replacement response, not a patch.",
            "Return exactly one candidate set for every required_service_id.",
            "Include each service ID at most once within its candidate set.",
            "Include exactly one gold candidate and two to five distinct alternatives.",
        ],
    }
    required_descriptors = [
        descriptor_summary(registry[service_id])
        for service_id in required_ids
        if service_id in registry
    ]
    candidate_index = [
        compact_descriptor_summary(descriptor)
        for service_id, descriptor in sorted(registry.items())
        if service_id not in required_ids
    ]
    return "\n\n".join(
        [
            "# Task",
            DISTRACTOR_TASK,
            "# Mandatory correction after rejected prior response",
            json.dumps(correction, indent=2, sort_keys=True),
            "# Reviewed required-service mapping",
            json.dumps(required_mapping, indent=2, sort_keys=True),
            "# Full descriptors for required services",
            json.dumps(required_descriptors, indent=2, sort_keys=True),
            "# Compact candidate-service index",
            json.dumps(candidate_index, indent=2, sort_keys=True),
            "# Active pipeline manifest",
            json.dumps(pipeline.manifest, indent=2, sort_keys=True),
            "# Active public description",
            pipeline.description,
            "# Active internal companion specification",
            json.dumps(pipeline.internal_spec, indent=2, sort_keys=True),
        ]
    )


def process_required(
    settings: RunSettings,
    pipelines: list[PipelineSource],
    corpus_pipelines: list[PipelineSource],
    execute: bool,
) -> None:
    registry_path = settings.run_root / "registry" / "required"
    response_path = settings.run_root / "responses" / "required"
    prompt_path = settings.run_root / "prompts" / "required"
    registry = load_registry(registry_path)
    corpus_index = build_corpus_index(corpus_pipelines)
    client = OpenAI() if execute else None

    for pipeline in pipelines:
        output_file = response_path / f"{pipeline.benchmark_id.replace(':', '__')}.json"
        prompt = build_prompt("required", pipeline, corpus_index, registry)
        write_json(
            prompt_path / f"{pipeline.benchmark_id.replace(':', '__')}.json",
            {
                "benchmark_id": pipeline.benchmark_id,
                "model": settings.model,
                "max_output_tokens": settings.max_output_tokens,
                "temperature": settings.temperature,
                "reasoning": {
                    "effort": settings.reasoning_effort,
                    "summary": settings.reasoning_summary,
                },
                "prompt": prompt,
            },
        )
        if output_file.exists():
            print(f"skip completed required response: {pipeline.benchmark_id}")
            continue
        attempt_path = latest_attempt(settings, "required", pipeline)
        if attempt_path is not None:
            metadata = json.loads(attempt_path.read_text(encoding="utf-8"))
            parsed = RequiredServiceResponse.model_validate(metadata["parsed"])
            accept_required_response(
                settings,
                pipeline,
                parsed,
                metadata,
                registry,
                registry_path,
                output_file,
            )
            print(f"recovered saved attempt: {attempt_path.name}")
            continue
        if not execute:
            print(f"planned required response: {pipeline.benchmark_id}")
            continue

        response, parsed_model = call_model(
            client,
            settings,
            prompt,
            RequiredServiceResponse,
            pipeline,
            "required",
        )
        parsed = RequiredServiceResponse.model_validate(parsed_model)
        metadata = response_metadata(response, parsed, prompt)
        write_attempt(settings, "required", pipeline, metadata)
        accept_required_response(
            settings,
            pipeline,
            parsed,
            metadata,
            registry,
            registry_path,
            output_file,
        )


def load_required_mapping(settings: RunSettings, pipeline: PipelineSource) -> dict[str, Any]:
    path = (
        settings.run_root
        / "responses"
        / "required"
        / f"{pipeline.benchmark_id.replace(':', '__')}.json"
    )
    if not path.exists():
        raise FileNotFoundError(f"Missing required response for {pipeline.benchmark_id}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["parsed"]


def validate_candidate_sets(
    parsed: DistractorServiceResponse,
    required_mapping: dict[str, Any],
    registry: dict[str, dict[str, Any]],
) -> None:
    required_ids = {
        service_id
        for item in required_mapping["step_accounting"]
        for service_id in item["required_service_ids"]
    }
    received_list = [item.required_service_id for item in parsed.candidate_sets]
    received_ids = set(received_list)
    if len(received_list) != len(received_ids):
        raise ValueError("A required service has more than one candidate set")
    if received_ids != required_ids:
        raise ValueError(
            "Candidate-set coverage mismatch: "
            f"expected={sorted(required_ids)}, received={sorted(received_ids)}"
        )
    new_ids = {item.service_id for item in parsed.new_distractor_services}
    duplicate_new = sorted(new_ids & set(registry))
    if duplicate_new:
        raise ValueError(f"Distractor proposals collide with registry IDs: {duplicate_new}")
    known = set(registry) | new_ids
    for candidate_set in parsed.candidate_sets:
        candidate_ids = [item.service_id for item in candidate_set.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError(f"Duplicate candidates in {candidate_set.candidate_set_id}")
        unknown = sorted(set(candidate_ids) - known)
        if unknown:
            raise ValueError(
                f"Unknown candidates in {candidate_set.candidate_set_id}: {unknown}"
            )
        gold = [item for item in candidate_set.candidates if item.label == "gold"]
        if len(gold) != 1 or gold[0].service_id != candidate_set.required_service_id:
            raise ValueError(
                f"{candidate_set.candidate_set_id} must contain exactly one correct gold relation"
            )


def snake_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not normalized or not normalized[0].isalpha():
        normalized = f"id_{normalized}"
    return normalized


def canonical_candidate_set_id(
    pipeline: PipelineSource,
    required_service_id: str,
) -> str:
    return (
        f"{snake_identifier(pipeline.benchmark_id)}_"
        f"{snake_identifier(required_service_id)}_candidates"
    )


def namespace_candidate_set_ids(
    pipeline: PipelineSource,
    parsed: DistractorServiceResponse,
) -> list[dict[str, str]]:
    normalizations = []
    for candidate_set in parsed.candidate_sets:
        canonical = canonical_candidate_set_id(
            pipeline,
            candidate_set.required_service_id,
        )
        if candidate_set.candidate_set_id == canonical:
            continue
        normalizations.append(
            {
                "from_candidate_set_id": candidate_set.candidate_set_id,
                "to_candidate_set_id": canonical,
                "reason": "global_pipeline_namespace",
            }
        )
        candidate_set.candidate_set_id = canonical
    return normalizations


def normalize_duplicate_gold_candidates(
    parsed: DistractorServiceResponse,
) -> list[dict[str, str]]:
    """Keep one gold copy of a candidate set's required service."""
    normalizations = []
    for candidate_set in parsed.candidate_sets:
        gold = [
            item
            for item in candidate_set.candidates
            if item.label == "gold"
            and item.service_id == candidate_set.required_service_id
        ]
        if not gold:
            continue
        retained_gold = False
        corrected = []
        for candidate in candidate_set.candidates:
            if candidate.service_id != candidate_set.required_service_id:
                corrected.append(candidate)
                continue
            if candidate.label == "gold" and not retained_gold:
                corrected.append(candidate)
                retained_gold = True
                continue
            normalizations.append(
                {
                    "candidate_set_id": candidate_set.candidate_set_id,
                    "service_id": candidate.service_id,
                    "removed_label": candidate.label,
                    "reason": "duplicate_copy_of_required_gold_service",
                }
            )
        candidate_set.candidates = corrected
    return normalizations


def accept_distractor_response(
    settings: RunSettings,
    pipeline: PipelineSource,
    parsed: DistractorServiceResponse,
    metadata: dict[str, Any],
    required_mapping: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    registry_path: Path,
    output_file: Path,
) -> None:
    normalizations = normalize_duplicate_gold_candidates(parsed)
    validate_candidate_sets(parsed, required_mapping, registry)
    if normalizations:
        metadata["parsed"] = parsed.model_dump(mode="json")
        metadata.setdefault("normalizations", []).extend(normalizations)
    descriptors = []
    for proposal in parsed.new_distractor_services:
        descriptor = materialize_descriptor(proposal, pipeline.benchmark_id, settings)
        validate_descriptor(descriptor)
        descriptors.append(descriptor)
    for descriptor in descriptors:
        registry[descriptor["service_id"]] = descriptor
    for service_id, descriptor in sorted(registry.items()):
        write_yaml(registry_path / f"{service_id}.yaml", descriptor)
    write_json(output_file, metadata)
    print(
        f"completed distractor response: {pipeline.benchmark_id} "
        f"({len(descriptors)} new)"
    )


def process_distractors(
    settings: RunSettings,
    pipelines: list[PipelineSource],
    corpus_pipelines: list[PipelineSource],
    execute: bool,
) -> None:
    required_registry_path = settings.run_root / "registry" / "required"
    all_registry_path = settings.run_root / "registry" / "all"
    response_path = settings.run_root / "responses" / "distractors"
    prompt_path = settings.run_root / "prompts" / "distractors"
    required_registry = load_registry(required_registry_path)
    if not required_registry:
        raise ValueError("Required registry is empty; complete the required phase first.")
    registry = load_registry(all_registry_path) or dict(required_registry)
    corpus_index = build_corpus_index(corpus_pipelines)
    client = OpenAI() if execute else None

    for pipeline in pipelines:
        required_mapping = load_required_mapping(settings, pipeline)
        output_file = response_path / f"{pipeline.benchmark_id.replace(':', '__')}.json"
        prompt = build_prompt(
            "distractors",
            pipeline,
            corpus_index,
            registry,
            required_mapping,
        )
        write_json(
            prompt_path / f"{pipeline.benchmark_id.replace(':', '__')}.json",
            {
                "benchmark_id": pipeline.benchmark_id,
                "model": settings.model,
                "prompt": prompt,
            },
        )
        if output_file.exists():
            print(f"skip completed distractor response: {pipeline.benchmark_id}")
            continue
        attempt_path = latest_attempt(settings, "distractors", pipeline)
        if attempt_path is not None:
            metadata = json.loads(attempt_path.read_text(encoding="utf-8"))
            parsed = DistractorServiceResponse.model_validate(metadata["parsed"])
            try:
                accept_distractor_response(
                    settings,
                    pipeline,
                    parsed,
                    metadata,
                    required_mapping,
                    registry,
                    all_registry_path,
                    output_file,
                )
            except ValueError as exc:
                reject_attempt(attempt_path, exc)
                if not execute:
                    raise
                prompt = distractor_retry_prompt(
                    pipeline,
                    required_mapping,
                    registry,
                    exc,
                )
                write_json(
                    prompt_path
                    / f"{pipeline.benchmark_id.replace(':', '__')}.json",
                    {
                        "benchmark_id": pipeline.benchmark_id,
                        "model": settings.model,
                        "prompt": prompt,
                        "retry_of_rejected_attempt": attempt_path.name,
                    },
                )
                print(
                    f"rejected saved attempt: {attempt_path.name}; "
                    "requesting a corrected replacement"
                )
            else:
                print(f"recovered saved attempt: {attempt_path.name}")
                continue
        if not execute:
            print(f"planned distractor response: {pipeline.benchmark_id}")
            continue

        response, parsed_model = call_model(
            client,
            settings,
            prompt,
            DistractorServiceResponse,
            pipeline,
            "distractors",
        )
        parsed = DistractorServiceResponse.model_validate(parsed_model)
        metadata = response_metadata(response, parsed, prompt)
        write_attempt(settings, "distractors", pipeline, metadata)
        accept_distractor_response(
            settings,
            pipeline,
            parsed,
            metadata,
            required_mapping,
            registry,
            all_registry_path,
            output_file,
        )


def expected_response_names(pipelines: list[PipelineSource]) -> set[str]:
    return {f"{item.benchmark_id.replace(':', '__')}.json" for item in pipelines}


def require_complete_phase(
    settings: RunSettings,
    pipelines: list[PipelineSource],
    phase: str,
) -> None:
    response_root = settings.run_root / "responses" / phase
    actual = {path.name for path in response_root.glob("*.json")}
    missing = sorted(expected_response_names(pipelines) - actual)
    if missing:
        raise ValueError(
            f"Cannot finalize: {phase} phase is missing {len(missing)} responses. "
            f"First missing entries: {missing[:5]}"
        )


def capability_terms(descriptor: dict[str, Any]) -> set[str]:
    values = [
        descriptor["service_id"],
        descriptor["capability"]["summary"],
        *descriptor["capability"]["operations"],
        *descriptor["capability"]["keywords"],
    ]
    text = " ".join(values).lower().replace("_", " ").replace("-", " ")
    return {
        token.strip(".,:;()[]{}")
        for token in text.split()
        if len(token.strip(".,:;()[]{}")) >= 3
    }


def potential_duplicate_pairs(
    registry: dict[str, dict[str, Any]],
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    pairs = []
    items = sorted(registry.items())
    for index, (left_id, left) in enumerate(items):
        left_terms = capability_terms(left)
        for right_id, right in items[index + 1 :]:
            right_terms = capability_terms(right)
            union = left_terms | right_terms
            score = len(left_terms & right_terms) / len(union) if union else 0.0
            if score >= threshold:
                pairs.append(
                    {
                        "left_service_id": left_id,
                        "right_service_id": right_id,
                        "jaccard_score": round(score, 3),
                    }
                )
    return sorted(pairs, key=lambda item: item["jaccard_score"], reverse=True)


def curated_variant_descriptor(
    settings: RunSettings,
    registry: dict[str, dict[str, Any]],
    source_service_id: str,
    service_id: str,
    display_name: str,
    summary: str,
    limitations: list[str],
    lifecycle: dict[str, Any],
    policy_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    descriptor = copy.deepcopy(registry[source_service_id])
    descriptor["service_id"] = service_id
    descriptor["version"] = "0.9.0" if lifecycle["status"] == "deprecated" else "1.0.0"
    descriptor["display_name"] = display_name
    descriptor["capability"]["summary"] = summary
    descriptor["capability"]["limitations"] = limitations
    descriptor["lifecycle"] = lifecycle
    for contract in descriptor["contracts"]:
        if contract["target"] == source_service_id:
            contract["target"] = service_id
    slug = service_id.replace("_", "-")
    descriptor["invocation"].update(
        {
            "template_name": f"{slug}-v1",
            "command": ["python", "-m", f"prompt2serviceflow_services.{service_id}"],
            "implementation_ref": f"services/implementations/{service_id}",
        }
    )
    if policy_updates:
        descriptor["policies"].update(policy_updates)
    descriptor["provenance"] = {
        "origin": "curated",
        "owner": settings.owner,
        "created_at": settings.created_at,
        "review_status": "reviewed",
        "source_refs": [f"catalog-curation:{settings.catalog_version}"],
        "notes": [
            f"Curated supplementary service derived from {source_service_id}.",
            "Lifecycle and policy metadata reflect catalogue governance constraints.",
        ],
    }
    return descriptor


def generic_escape_hatch_descriptor(
    settings: RunSettings,
    service_id: str,
    display_name: str,
    category: str,
    summary: str,
    parameter_name: str,
) -> dict[str, Any]:
    slug = service_id.replace("_", "-")
    output_name = "transformed_artifacts" if category == "Transformer" else "adapted_artifacts"
    return {
        "schema_version": "0.1.0",
        "service_id": service_id,
        "version": "1.0.0",
        "display_name": display_name,
        "category": category,
        "capability": {
            "summary": summary,
            "operations": [
                "Read zero or more bound workflow artifacts.",
                "Execute only a reviewed, registered implementation.",
                "Emit transformed artifacts and an observable execution report.",
            ],
            "keywords": [
                "reviewed extension",
                "generic adapter",
                "escape hatch",
                "custom transformation",
            ],
            "limitations": [
                "Requires prior human review and registration of the implementation.",
                "Provides weaker domain-specific contracts than dedicated services.",
                "Must not be selected when a specific compatible service is available.",
            ],
        },
        "lifecycle": {"status": "active"},
        "interface": {
            "inputs": [
                {
                    "name": "input_artifacts",
                    "description": "Artifacts supplied to the reviewed extension.",
                    "channel": "artifact",
                    "data_type": "any",
                    "required": False,
                    "cardinality": "many",
                    "sensitivity": "restricted",
                }
            ],
            "outputs": [
                {
                    "name": output_name,
                    "description": "Artifacts produced by the reviewed extension.",
                    "channel": "artifact",
                    "data_type": "any",
                    "required": True,
                    "cardinality": "many",
                    "sensitivity": "restricted",
                },
                {
                    "name": "execution_report",
                    "description": "Observable execution status and produced artifact references.",
                    "channel": "artifact",
                    "data_type": "status",
                    "media_type": "application/json",
                    "schema_ref": "schema://reviewed_extension_execution_report/v1",
                    "required": True,
                    "cardinality": "one",
                    "sensitivity": "internal",
                },
            ],
            "parameters": [
                {
                    "name": parameter_name,
                    "description": "Identifier of the reviewed implementation to invoke.",
                    "type": "string",
                    "required": True,
                    "pattern": "^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$",
                },
                {
                    "name": "extension_parameters",
                    "description": "Implementation-specific parameters reviewed with the extension.",
                    "type": "object",
                    "required": False,
                },
            ],
            "secrets": [],
        },
        "contracts": [
            {
                "contract_id": "reviewed_extension_identifier",
                "type": "precondition",
                "applies_to": "parameter",
                "target": parameter_name,
                "description": "The extension identifier must resolve to a reviewed implementation.",
                "expression": f"reviewed_registry_contains({parameter_name})",
            },
            {
                "contract_id": "reviewed_extension_execution_report",
                "type": "json_schema",
                "applies_to": "output",
                "target": "execution_report",
                "description": "The report exposes success and produced artifact references.",
                "schema_ref": "schema://reviewed_extension_execution_report/v1",
                "expression": (
                    '{"type":"object","required":["success","implementation_id",'
                    '"produced_artifacts"],"properties":{"success":{"type":"boolean"},'
                    '"implementation_id":{"type":"string"},"produced_artifacts":'
                    '{"type":"array","items":{"type":"string"}},"errors":{"type":"array",'
                    '"items":{"type":"string"}}}}'
                ),
            },
        ],
        "invocation": {
            "type": "argo_workflow_template",
            "template_name": f"{slug}-v1",
            "template_entrypoint": "main",
            "image": "prompt2serviceflow/runtime:0.1.0",
            "command": ["python", "-m", f"prompt2serviceflow_services.{service_id}"],
            "implementation_ref": f"services/implementations/{service_id}",
            "mock_supported": True,
        },
        "policies": {
            "network_access": "optional",
            "allowed_network_targets": [],
            "secret_access": "optional",
            "retry_safe": False,
            "idempotency": "unknown",
            "idempotency_notes": "Depends on the reviewed implementation.",
            "default_timeout_seconds": 600,
            "data_sensitivity": [
                "public",
                "internal",
                "confidential",
                "restricted",
                "pii",
                "phi",
                "financial",
            ],
            "resources": {"cpu": "250m", "memory": "256Mi", "gpu": 0},
            "governance_notes": [
                "Use requires explicit human approval and a registered implementation.",
                "Selection frequency must be reported as benchmark escape-hatch usage.",
            ],
        },
        "compatibility": {
            "runtime": {"target": "argo-workflows", "minimum_version": "3.5.0"},
            "supported_architectures": ["amd64", "arm64"],
            "incompatible_services": [],
        },
        "provenance": {
            "origin": "curated",
            "owner": settings.owner,
            "created_at": settings.created_at,
            "review_status": "reviewed",
            "source_refs": [f"catalog-curation:{settings.catalog_version}"],
            "notes": [
                "Controlled generic extension maintained in the curated catalogue.",
                "Use requires explicit review when a dedicated capability is unavailable.",
            ],
        },
    }


def build_supplemental_registry(
    settings: RunSettings,
    registry: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    deprecated = [
        (
            "csv_tabular_schema_validating_loader",
            "legacy_csv_schema_validator",
            "Legacy CSV Schema Validator",
            "Validates CSV columns using a deprecated legacy validation interface.",
            [
                "Deprecated; new compositions must use the documented replacement.",
                "Retained only for compatibility with legacy catalogue clients.",
            ],
        ),
        (
            "http_json_request_extractor",
            "legacy_http_json_extractor",
            "Legacy HTTP JSON Extractor",
            "Fetches JSON over HTTP using a deprecated legacy extraction interface.",
            [
                "Deprecated; new compositions must use the documented replacement.",
                "Retained only for compatibility with legacy catalogue clients.",
            ],
        ),
        (
            "tabular_dataset_database_loader",
            "legacy_database_table_loader",
            "Legacy Database Table Loader",
            "Loads tabular data into a database table using a deprecated legacy interface.",
            [
                "Deprecated; new compositions must use the documented replacement.",
                "Retained only for compatibility with legacy workflows.",
            ],
        ),
    ]
    result = {}
    for source_id, service_id, display_name, summary, limitations in deprecated:
        result[service_id] = curated_variant_descriptor(
            settings,
            registry,
            source_id,
            service_id,
            display_name,
            summary,
            limitations,
            {
                "status": "deprecated",
                "deprecated_since": settings.catalog_version,
                "replacement": {"service_id": source_id, "version": "1.0.0"},
            },
        )

    result["open_network_http_json_requester"] = curated_variant_descriptor(
        settings,
        registry,
        "http_json_request_extractor",
        "open_network_http_json_requester",
        "Open-Network HTTP JSON Requester",
        "Executes JSON HTTP requests against arbitrary caller-provided endpoints.",
        [
            "Does not enforce an endpoint allowlist.",
            "Not approved for confidential, restricted, PII, PHI, or financial payloads.",
        ],
        {"status": "experimental"},
        {
            "data_sensitivity": ["public", "internal"],
            "governance_notes": [
                "Arbitrary endpoint access is permitted without allowlist enforcement.",
                "Use with sensitive data is prohibited.",
            ],
        },
    )
    result["unreviewed_postgres_sql_executor"] = curated_variant_descriptor(
        settings,
        registry,
        "postgres_parameterized_sql_executor",
        "unreviewed_postgres_sql_executor",
        "Unreviewed PostgreSQL SQL Executor",
        "Executes caller-supplied PostgreSQL statements without a reviewed SQL allowlist.",
        [
            "SQL text is not constrained to a reviewed statement set.",
            "Not approved for confidential, restricted, PII, PHI, or financial data.",
        ],
        {"status": "experimental"},
        {
            "data_sensitivity": ["public", "internal"],
            "governance_notes": [
                "Caller-supplied SQL is executed without allowlist review.",
                "Use with sensitive data or production databases is prohibited.",
            ],
        },
    )
    result["unrestricted_email_notification_sender"] = curated_variant_descriptor(
        settings,
        registry,
        "email_notification_sender",
        "unrestricted_email_notification_sender",
        "Unrestricted Email Notification Sender",
        "Sends email to caller-provided recipients without recipient-domain restrictions.",
        [
            "Does not enforce approved recipient domains.",
            "Does not provide idempotency or duplicate-delivery protection.",
        ],
        {"status": "experimental"},
        {
            "data_sensitivity": ["public", "internal"],
            "governance_notes": [
                "Recipient domains are not restricted.",
                "Use with PII, PHI, financial, confidential, or restricted content is prohibited.",
            ],
        },
    )
    result["reviewed_python_udf_transformer"] = generic_escape_hatch_descriptor(
        settings,
        "reviewed_python_udf_transformer",
        "Reviewed Python UDF Transformer",
        "Transformer",
        "Executes a reviewed Python transformation extension when no specific service fits.",
        "udf_id",
    )
    result["reviewed_domain_adapter"] = generic_escape_hatch_descriptor(
        settings,
        "reviewed_domain_adapter",
        "Reviewed Domain Adapter",
        "DomainAdapter",
        "Executes a reviewed domain adapter when no dedicated catalogue capability fits.",
        "adapter_id",
    )
    for descriptor in result.values():
        validate_descriptor(descriptor)
    return result


def descriptor_search_text(descriptor: dict[str, Any]) -> str:
    values = [
        descriptor["service_id"],
        descriptor["category"],
        descriptor["capability"]["summary"],
        *descriptor["capability"]["keywords"],
    ]
    return " ".join(values).lower().replace("_", " ")


def supplemental_candidates_for(
    required: dict[str, Any],
) -> list[tuple[str, str, str]]:
    text = descriptor_search_text(required)
    service_id = required["service_id"]
    service_tokens = set(service_id.split("_"))
    category = required["category"]
    sensitive = bool(
        set(required["policies"]["data_sensitivity"])
        & {"confidential", "restricted", "pii", "phi", "financial"}
    )
    candidates = []
    if (
        "csv" in text
        and any(
            term in service_tokens
            for term in (
                "loader",
                "validator",
                "validating",
                "formatter",
                "normalizer",
                "standardizer",
            )
        )
    ):
        candidates.append(
            (
                "legacy_csv_schema_validator",
                "deprecated_or_incompatible",
                "The legacy service overlaps on CSV loading, validation, or normalization but is deprecated and retained only for compatibility.",
            )
        )
    if any(term in text for term in ("http", "api", "graphql", "json endpoint")):
        candidates.append(
            (
                "legacy_http_json_extractor",
                "deprecated_or_incompatible",
                "The legacy extractor overlaps on remote JSON access but is deprecated and retained only for compatibility.",
            )
        )
        if sensitive:
            candidates.append(
                (
                    "open_network_http_json_requester",
                    "policy_incompatible",
                    "The requester can reach the endpoint but permits arbitrary network targets and is not approved for sensitive data.",
                )
            )
    if category == "Loader" or any(
        term in text for term in ("database load", "warehouse load", "table loader")
    ):
        candidates.append(
            (
                "legacy_database_table_loader",
                "deprecated_or_incompatible",
                "The legacy loader targets database tables but is deprecated and retained only for compatibility.",
            )
        )
    if (
        sensitive
        and category in {"Loader", "Extractor", "Maintenance"}
        and any(term in text for term in ("sql", "postgres"))
    ):
        candidates.append(
            (
                "unreviewed_postgres_sql_executor",
                "policy_incompatible",
                "The executor overlaps on database effects but permits unreviewed SQL and is prohibited for sensitive data.",
            )
        )
    if "email" in text:
        candidates.append(
            (
                "unrestricted_email_notification_sender",
                "policy_incompatible",
                "The sender overlaps on email delivery but lacks recipient restrictions and sensitive-content approval.",
            )
        )
    if category in {
        "Transformer",
        "Integrator",
        "Aggregator",
        "Reconciler",
        "PrivacyService",
        "ScoringService",
        "QualityCheck",
        "DataProfiler",
    }:
        candidates.append(
            (
                "reviewed_python_udf_transformer",
                "generic_escape_hatch",
                "A reviewed UDF could imitate the transformation, but it is an overly generic escape hatch with weaker contracts.",
            )
        )
    if category not in {"Notifier", "Maintenance"}:
        candidates.append(
            (
                "reviewed_domain_adapter",
                "generic_escape_hatch",
                "A reviewed domain adapter could wrap the behavior, but it is less specific and less contract-grounded than the required service.",
            )
        )
    return candidates


def curate_catalog(
    settings: RunSettings,
    pipelines: list[PipelineSource],
) -> None:
    require_complete_phase(settings, pipelines, "required")
    require_complete_phase(settings, pipelines, "distractors")
    report_path = settings.run_root / "reports" / "catalog_curation.json"
    previous_report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else {}
    )
    registry_path = settings.run_root / "registry" / "all"
    registry = load_registry(registry_path)
    for service_id in SUPPLEMENTAL_SERVICE_IDS:
        registry.pop(service_id, None)
    supplemental = build_supplemental_registry(settings, registry)
    registry.update(supplemental)
    for service_id, descriptor in sorted(registry.items()):
        write_yaml(registry_path / f"{service_id}.yaml", descriptor)

    pipeline_by_id = {item.pipeline_id: item for item in pipelines}
    response_root = settings.run_root / "responses" / "distractors"
    additions = []
    id_normalizations = []
    label_counts: dict[str, int] = {}
    service_counts: dict[str, int] = {}
    global_ids = set()

    for path in sorted(response_root.glob("*.json")):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        parsed = DistractorServiceResponse.model_validate(metadata["parsed"])
        pipeline = pipeline_by_id[parsed.pipeline_id]
        parsed_sets = []
        for candidate_set in parsed.candidate_sets:
            candidate_set.candidates = [
                item
                for item in candidate_set.candidates
                if item.service_id not in SUPPLEMENTAL_SERVICE_IDS
            ]
            parsed_sets.append(candidate_set)
        parsed.candidate_sets = parsed_sets
        id_normalizations.extend(
            {
                "pipeline_id": pipeline.pipeline_id,
                **item,
            }
            for item in namespace_candidate_set_ids(pipeline, parsed)
        )

        for candidate_set in parsed.candidate_sets:
            if candidate_set.candidate_set_id in global_ids:
                raise ValueError(
                    f"Duplicate global candidate_set_id: {candidate_set.candidate_set_id}"
                )
            global_ids.add(candidate_set.candidate_set_id)
            if len(candidate_set.candidates) >= 6:
                continue
            required = registry[candidate_set.required_service_id]
            existing = {item.service_id for item in candidate_set.candidates}
            applicable = [
                item
                for item in supplemental_candidates_for(required)
                if item[0] not in existing
            ]
            if not applicable:
                continue
            service_id, label, rationale = min(
                applicable,
                key=lambda item: (
                    label_counts.get(item[1], 0),
                    service_counts.get(item[0], 0),
                    item[0],
                ),
            )
            candidate_set.candidates.append(
                CandidateRelation(
                    service_id=service_id,
                    label=label,
                    rationale=rationale,
                )
            )
            label_counts[label] = label_counts.get(label, 0) + 1
            service_counts[service_id] = service_counts.get(service_id, 0) + 1
            additions.append(
                {
                    "pipeline_id": pipeline.pipeline_id,
                    "candidate_set_id": candidate_set.candidate_set_id,
                    "required_service_id": candidate_set.required_service_id,
                    "service_id": service_id,
                    "label": label,
                }
            )

        required_mapping = load_required_mapping(settings, pipeline)
        validate_candidate_sets(parsed, required_mapping, registry)
        metadata["parsed"] = parsed.model_dump(mode="json")
        metadata["catalog_curation"] = {
            "policy_version": settings.catalog_version,
            "candidate_ids_namespaced": True,
            "supplemental_candidate_limit_per_set": 1,
        }
        write_json(path, metadata)

    previous_normalizations = previous_report.get("candidate_id_normalizations", [])
    if previous_normalizations:
        known_targets = {
            item["to_candidate_set_id"] for item in id_normalizations
        }
        id_normalizations = [
            *id_normalizations,
            *(
                item
                for item in previous_normalizations
                if item["to_candidate_set_id"] not in known_targets
            ),
        ]
    report = {
        "catalog_version": settings.catalog_version,
        "run_id": settings.run_id,
        "required_service_count": len(registry) - len(supplemental),
        "supplemental_service_count": len(supplemental),
        "total_service_count": len(registry),
        "candidate_set_count": len(global_ids),
        "candidate_set_ids_globally_unique": True,
        "candidate_id_normalization_count": len(id_normalizations),
        "supplemental_relation_count": len(additions),
        "supplemental_label_counts": dict(sorted(label_counts.items())),
        "supplemental_service_usage": dict(sorted(service_counts.items())),
        "supplemental_services": sorted(supplemental),
        "policy": {
            "contextual_distractors_remain_primary": True,
            "maximum_supplemental_candidates_per_set": 1,
            "maximum_candidates_per_set": 6,
            "supplemental_classes": [
                "deprecated_or_incompatible",
                "policy_incompatible",
                "generic_escape_hatch",
            ],
        },
        "candidate_id_normalizations": id_normalizations,
        "supplemental_relations": additions,
    }
    write_json(report_path, report)
    print(
        f"curated catalog: {len(registry)} services, {len(global_ids)} candidate sets, "
        f"{len(additions)} supplemental relations"
    )


def write_snapshot_checksums(snapshot_root: Path) -> None:
    checksum_path = snapshot_root / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.relative_to(snapshot_root).as_posix()}"
        for path in sorted(snapshot_root.rglob("*"))
        if path.is_file() and path != checksum_path
    ]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_curated_catalog(
    settings: RunSettings,
    pipelines: list[PipelineSource],
    registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    report_path = settings.run_root / "reports" / "catalog_curation.json"
    if not report_path.exists():
        raise ValueError("Catalog has not been curated; run the curate command first.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("catalog_version") != settings.catalog_version:
        raise ValueError("Catalog curation report version does not match the run.")
    if not report.get("candidate_set_ids_globally_unique"):
        raise ValueError("Catalog curation did not establish globally unique candidate IDs.")
    missing_supplemental = sorted(SUPPLEMENTAL_SERVICE_IDS - set(registry))
    if missing_supplemental:
        raise ValueError(
            f"Curated registry is missing supplemental services: {missing_supplemental}"
        )

    candidate_ids = []
    label_counts: dict[str, int] = {}
    size_counts: dict[str, int] = {}
    response_root = settings.run_root / "responses" / "distractors"
    pipeline_by_name = {
        f"{item.benchmark_id.replace(':', '__')}.json": item for item in pipelines
    }
    for path in sorted(response_root.glob("*.json")):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not metadata.get("catalog_curation", {}).get("candidate_ids_namespaced"):
            raise ValueError(f"Distractor response is not curated: {path.name}")
        parsed = DistractorServiceResponse.model_validate(metadata["parsed"])
        pipeline = pipeline_by_name[path.name]
        validate_candidate_sets(
            parsed,
            load_required_mapping(settings, pipeline),
            registry,
        )
        for candidate_set in parsed.candidate_sets:
            candidate_ids.append(candidate_set.candidate_set_id)
            size = str(len(candidate_set.candidates))
            size_counts[size] = size_counts.get(size, 0) + 1
            for candidate in candidate_set.candidates:
                label_counts[candidate.label] = label_counts.get(candidate.label, 0) + 1
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Candidate-set IDs are not globally unique.")
    if len(candidate_ids) != report.get("candidate_set_count"):
        raise ValueError("Candidate-set count differs from the curation report.")
    return {
        "candidate_set_count": len(candidate_ids),
        "candidate_size_counts": dict(sorted(size_counts.items())),
        "candidate_label_counts": dict(sorted(label_counts.items())),
        "curation": report,
    }


def finalize_catalog(settings: RunSettings, pipelines: list[PipelineSource]) -> None:
    require_complete_phase(settings, pipelines, "required")
    require_complete_phase(settings, pipelines, "distractors")
    all_registry_path = settings.run_root / "registry" / "all"
    registry = load_registry(all_registry_path)
    if not registry:
        raise ValueError("Combined registry is empty; complete the distractor phase first.")
    curated_audit = validate_curated_catalog(settings, pipelines, registry)

    snapshot_root = (
        ROOT / "benchmark" / "catalog" / "snapshots" / settings.catalog_version
    )
    services_root = snapshot_root / "services"
    if snapshot_root.exists() and any(snapshot_root.iterdir()):
        raise FileExistsError(
            f"Snapshot {snapshot_root} already exists and will not be overwritten."
        )
    services_root.mkdir(parents=True)
    entries = []
    for service_id, descriptor in sorted(registry.items()):
        validate_descriptor(descriptor)
        descriptor_path = services_root / f"{service_id}.yaml"
        write_yaml(descriptor_path, descriptor)
        entries.append(
            {
                "service_id": service_id,
                "version": descriptor["version"],
                "category": descriptor["category"],
                "descriptor_path": descriptor_path.relative_to(snapshot_root).as_posix(),
                "sha256": sha256_file(descriptor_path),
            }
        )

    catalog = {
        "catalog_id": "serviceflow_catalog",
        "version": settings.catalog_version,
        "created_at": settings.created_at,
        "descriptor_schema": "schemas/service_descriptor.schema.json",
        "generation": {
            "run_id": settings.run_id,
            "model": settings.model,
            "reasoning_effort": settings.reasoning_effort,
            "max_output_tokens": settings.max_output_tokens,
            "temperature": settings.temperature,
            "splits": list(settings.splits),
            "pipeline_count": len(pipelines),
        },
        "service_count": len(entries),
        "services": entries,
    }
    write_yaml(snapshot_root / "catalog.yaml", catalog)
    write_snapshot_checksums(snapshot_root)

    labels = []
    for path in sorted((settings.run_root / "responses" / "distractors").glob("*.json")):
        response = json.loads(path.read_text(encoding="utf-8"))
        labels.append(response["parsed"])
    review_root = (
        ROOT / "benchmark" / "catalog" / "review" / settings.catalog_version
    )
    review_root.mkdir(parents=True, exist_ok=True)
    write_json(
        review_root / "candidate_relationships.private.json",
        {
            "warning": "Hidden review data; exclude from model-visible candidate catalogs.",
            "catalog_version": settings.catalog_version,
            "pipelines": labels,
        },
    )
    category_counts: dict[str, int] = {}
    lifecycle_counts: dict[str, int] = {}
    for descriptor in registry.values():
        category = descriptor["category"]
        lifecycle = descriptor["lifecycle"]["status"]
        category_counts[category] = category_counts.get(category, 0) + 1
        lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1
    write_json(
        review_root / "catalog_review_report.json",
        {
            "catalog_version": settings.catalog_version,
            "service_count": len(registry),
            "category_counts": dict(sorted(category_counts.items())),
            "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
            "candidate_set_count": curated_audit["candidate_set_count"],
            "candidate_size_counts": curated_audit["candidate_size_counts"],
            "candidate_label_counts": curated_audit["candidate_label_counts"],
            "curation_policy": curated_audit["curation"]["policy"],
            "supplemental_service_count": curated_audit["curation"][
                "supplemental_service_count"
            ],
            "supplemental_relation_count": curated_audit["curation"][
                "supplemental_relation_count"
            ],
            "supplemental_service_usage": curated_audit["curation"][
                "supplemental_service_usage"
            ],
            "potential_duplicate_capabilities": potential_duplicate_pairs(registry),
            "notes": [
                "Potential duplicates use lexical Jaccard similarity and require human review.",
                "Candidate relationship labels are private and must not enter model-visible inputs.",
                "Contextual distractors are primary; curated supplements add at most one candidate per set.",
            ],
        },
    )
    print(f"wrote catalog snapshot: {snapshot_root} ({len(entries)} services)")


def show_status(settings: RunSettings, pipelines: list[PipelineSource]) -> None:
    required = list((settings.run_root / "responses" / "required").glob("*.json"))
    distractors = list((settings.run_root / "responses" / "distractors").glob("*.json"))
    required_services = load_registry(settings.run_root / "registry" / "required")
    all_services = load_registry(settings.run_root / "registry" / "all")
    curation_path = settings.run_root / "reports" / "catalog_curation.json"
    curation = (
        json.loads(curation_path.read_text(encoding="utf-8"))
        if curation_path.exists()
        else None
    )
    print(
        json.dumps(
            {
                "run_id": settings.run_id,
                "selected_pipelines": len(pipelines),
                "required_responses": len(required),
                "distractor_responses": len(distractors),
                "required_services": len(required_services),
                "all_services": len(all_services),
                "catalog_curated": curation is not None,
                "supplemental_services": (
                    curation["supplemental_service_count"] if curation else 0
                ),
                "candidate_sets": curation["candidate_set_count"] if curation else 0,
                "supplemental_relations": (
                    curation["supplemental_relation_count"] if curation else 0
                ),
            },
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("required", "distractors", "curate", "finalize", "status"),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--split",
        action="append",
        choices=("main", "validation", "extension"),
        help="Override configured splits; repeat for an intentional all-60 run.",
    )
    parser.add_argument(
        "--pipeline",
        action="append",
        default=[],
        help="Pipeline ID or benchmark ID; repeat to select several.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Make paid API calls. Without this flag, only prompts are rendered.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    settings = load_settings(config_path, args.run_id, args.split)
    initialize_run(settings, config_path)
    corpus_pipelines = load_pipelines(settings.splits)
    pipelines = selected_pipelines(
        corpus_pipelines,
        args.pipeline,
        args.limit,
    )
    if not pipelines:
        raise ValueError("No pipelines selected.")

    if args.command in {"required", "distractors"} and args.execute:
        load_dotenv(ROOT / ".env", override=False)
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set in the environment or .env")
    if args.command == "required":
        process_required(settings, pipelines, corpus_pipelines, args.execute)
    elif args.command == "distractors":
        process_distractors(settings, pipelines, corpus_pipelines, args.execute)
    elif args.command == "curate":
        if args.execute:
            raise ValueError("--execute is not used by curate")
        if args.pipeline or args.limit is not None:
            raise ValueError("curate always operates on the complete configured corpus")
        curate_catalog(settings, corpus_pipelines)
    elif args.command == "finalize":
        if args.execute:
            raise ValueError("--execute is not used by finalize")
        if args.pipeline or args.limit is not None:
            raise ValueError("finalize always operates on the complete configured corpus")
        finalize_catalog(settings, corpus_pipelines)
    else:
        show_status(settings, corpus_pipelines)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
