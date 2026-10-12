# Schema Design

The initial schema version is `0.1.0`.

## Service Descriptor

`schemas/service_descriptor.schema.json` defines one model-visible service
catalog entry. It covers:

- stable service ID and semantic version;
- capability and lifecycle;
- input/output ports, parameters, and secrets;
- data, semantic, precondition, and effect contracts;
- Argo WorkflowTemplate invocation;
- network, retry, idempotency, sensitivity, and resource policies;
- runtime compatibility and provenance.

The schema intentionally has `additionalProperties: false` and contains no
fields for `correct`, `gold`, `distractor`, or other benchmark-answer labels.
Those labels belong only in hidden instance gold files.

## ServiceFlowIR

`schemas/serviceflow_ir.schema.json` defines the authoritative composition:

- catalog and source provenance;
- normalized requirement and schedule;
- external systems;
- abstract service intents with evidence and uncertainty;
- control-flow edges, parallel groups, branches, and gates;
- artifacts and producer/consumer relationships;
- concrete service bindings;
- workflow and service policy overrides;
- pinned Argo runtime configuration;
- G0-G6 validation expectations.

JSON Schema enforces shape and primitive constraints. The semantic validator in
`prompt2serviceflow.validators.schema_validation` additionally checks:

- unique identifiers;
- complete intent bindings;
- valid intent, artifact, and external-system references;
- producer/consumer consistency;
- binding-to-intent artifact consistency;
- branch decision and gate references;
- complete, non-duplicated G0-G6 expectations.

`source_step_accounting` may classify each locked source step as `service`,
`orchestration`, `noop`, or `unresolvable`. Service-accounted steps name their
corresponding service intents; non-service dispositions must not invent
catalogue bindings. G1 checks exact source-step coverage.

An artifact may name multiple producers only when control flow makes them
mutually exclusive alternatives, such as the full and incremental branches of
a backup workflow. Each listed producer must declare the artifact as an
output. This represents one logical artifact without inventing a routing
service merely to satisfy a branch merge.

Bindings preserve all artifact mappings for a descriptor port with
cardinality `many`. Compact gold artifact mappings therefore encode one
artifact ID for a single-valued port and an ordered list of artifact IDs for a
many-valued port. Contract validation rejects repeated mappings to a
single-valued port.

## Examples

- `schemas/examples/http_json_fetcher.service.yaml`
- `schemas/examples/airvisual.serviceflow.yaml`
- `schemas/examples/data_quality_gate.serviceflow.yaml`

Validate them with:

```bash
python3 scripts/validate_artifact.py service-descriptor \
  schemas/examples/http_json_fetcher.service.yaml \
  --schema schemas/service_descriptor.schema.json

python3 scripts/validate_artifact.py serviceflow-ir \
  schemas/examples/airvisual.serviceflow.yaml \
  --schema schemas/serviceflow_ir.schema.json

python3 scripts/validate_artifact.py serviceflow-ir \
  schemas/examples/data_quality_gate.serviceflow.yaml \
  --schema schemas/serviceflow_ir.schema.json
```

Run all three validations with `make validate-schemas`.
