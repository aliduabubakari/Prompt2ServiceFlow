"""Structured-output models for service-catalog generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ServiceCategory = Literal[
    "Sensor",
    "Extractor",
    "QualityCheck",
    "DataProfiler",
    "Transformer",
    "Integrator",
    "Aggregator",
    "Reconciler",
    "PrivacyService",
    "ScoringService",
    "Loader",
    "Publisher",
    "ReportGenerator",
    "Notifier",
    "ExternalWorkflowAdapter",
    "Maintenance",
    "DomainAdapter",
]
DataType = Literal[
    "string",
    "integer",
    "number",
    "boolean",
    "object",
    "array",
    "json",
    "csv",
    "parquet",
    "text",
    "binary",
    "directory",
    "markdown",
    "image",
    "model",
    "table",
    "decision",
    "status",
    "notification",
    "any",
]
Sensitivity = Literal[
    "public",
    "internal",
    "confidential",
    "restricted",
    "pii",
    "phi",
    "financial",
]
AccessRequirement = Literal["forbidden", "optional", "required"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposedDataPort(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=3, max_length=240)
    channel: Literal["artifact", "parameter", "external_resource"]
    data_type: DataType
    media_type: str | None
    schema_ref: str | None
    required: bool
    cardinality: Literal["one", "many"]
    sensitivity: Sensitivity


class ProposedParameter(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=3, max_length=240)
    type: Literal["string", "integer", "number", "boolean", "object", "array"]
    required: bool
    enum_values: list[str]
    pattern: str | None
    minimum: float | None
    maximum: float | None


class ProposedSecret(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=3, max_length=240)
    required: bool
    environment_variable: str | None


class ProposedContract(StrictModel):
    contract_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    type: Literal["json_schema", "tabular_schema", "semantic", "precondition", "effect"]
    applies_to: Literal["input", "output", "parameter", "service"]
    target: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=3, max_length=240)
    schema_ref: str | None
    expression: str | None

    @model_validator(mode="after")
    def require_contract_definition(self) -> "ProposedContract":
        if not self.schema_ref and not self.expression:
            raise ValueError("a proposed contract requires schema_ref or expression")
        return self


class ServiceProposal(StrictModel):
    service_id: str = Field(
        pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$",
        max_length=55,
    )
    display_name: str = Field(min_length=1, max_length=120)
    category: ServiceCategory
    capability_summary: str = Field(min_length=10, max_length=300)
    operations: list[str] = Field(min_length=1, max_length=4)
    keywords: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(max_length=4)
    source_step_refs: list[str] = Field(min_length=1)
    inputs: list[ProposedDataPort]
    outputs: list[ProposedDataPort] = Field(min_length=1)
    parameters: list[ProposedParameter]
    secrets: list[ProposedSecret]
    contracts: list[ProposedContract] = Field(max_length=8)
    lifecycle_status: Literal["experimental", "active", "deprecated"]
    network_access: AccessRequirement
    allowed_network_targets: list[str]
    secret_access: AccessRequirement
    retry_safe: bool
    idempotency: Literal[
        "idempotent",
        "conditionally_idempotent",
        "non_idempotent",
        "unknown",
    ]
    idempotency_notes: str | None
    default_timeout_seconds: int | None = Field(default=None, ge=1)
    data_sensitivity: list[Sensitivity] = Field(min_length=1)
    governance_notes: list[str] = Field(max_length=4)
    rationale: str = Field(min_length=10, max_length=500)
    ambiguity: Literal["explicit", "strongly_inferred", "weakly_inferred"]


class StepAccounting(StrictModel):
    step_id: str
    disposition: Literal["service", "orchestration", "noop", "unresolvable"]
    required_service_ids: list[str]
    rationale: str = Field(max_length=500)


class ReusedService(StrictModel):
    service_id: str
    source_step_refs: list[str] = Field(min_length=1)
    rationale: str = Field(max_length=500)


class RequiredServiceResponse(StrictModel):
    pipeline_id: str
    pipeline_summary: str = Field(max_length=500)
    step_accounting: list[StepAccounting] = Field(min_length=1)
    reused_services: list[ReusedService]
    new_services: list[ServiceProposal]
    unresolved_requirements: list[str] = Field(max_length=8)
    review_notes: list[str] = Field(max_length=8)


DistractorLabel = Literal[
    "gold",
    "semantic_mismatch",
    "format_mismatch",
    "target_mismatch",
    "deprecated_or_incompatible",
    "policy_incompatible",
    "missing_required_output",
    "generic_escape_hatch",
    "contract_mismatch",
]


class CandidateRelation(StrictModel):
    service_id: str
    label: DistractorLabel
    rationale: str = Field(max_length=500)


class CandidateSet(StrictModel):
    candidate_set_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    required_service_id: str
    source_step_refs: list[str] = Field(min_length=1)
    candidates: list[CandidateRelation] = Field(min_length=3, max_length=6)


class DistractorServiceResponse(StrictModel):
    pipeline_id: str
    candidate_sets: list[CandidateSet]
    new_distractor_services: list[ServiceProposal]
    review_notes: list[str] = Field(max_length=8)
