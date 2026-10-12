# Extension-50 Batch 01

This batch is processed as a complete benchmark-generation unit: source review, catalogue-gap decisions, ServiceFlowIR, gold bindings, candidate labels, artifact mappings, fixtures, mock scripts, Argo output, G0-G6 validation, semantic hardening, and independent adjudication notes.

## Pipelines

| # | Pipeline | Track | Domain | Topology | Complexity | Steps |
|---:|---|---|---|---|---|---:|
| 1 | `medical_image_metadata_quality_check` | `image_document_multimodal` | Healthcare/Public Health | `linear` | `simple` | 5 |
| 2 | `satellite_change_report_assembler` | `image_document_multimodal` | Environmental/Energy | `staged` | `medium` | 7 |
| 3 | `scanned_claim_packet_extraction` | `image_document_multimodal` | Finance/Risk | `fan_out` | `complex` | 10 |
| 4 | `product_image_listing_enrichment` | `image_document_multimodal` | Retail/E-commerce | `fan_out` | `medium` | 7 |
| 5 | `identity_document_redaction` | `image_document_multimodal` | Legal/Compliance | `branch_gate` | `complex` | 10 |

## Batch Commands

```bash
python3 scripts/run_extension_benchmark.py --batch 1 --phase bootstrap
python3 scripts/author_extension_batch_01.py
python3 scripts/run_extension_benchmark.py --batch 1 --phase compile
python3 scripts/run_extension_benchmark.py --batch 1 --phase validate
python3 scripts/run_extension_benchmark.py --batch 1 --phase report
```

## Required Authoring Outputs Per Pipeline

- `gold/serviceflow.yaml` with complete source-step accounting.
- `gold/bindings.yaml` and `gold/artifact_mappings.yaml` compact projections.
- `candidates/candidate_sets.yaml` and private `gold/candidate_labels.yaml`.
- `contracts/artifacts/*.schema.json` where JSON artifacts need explicit contracts.
- `fixtures/inputs/*` with credential-free deterministic inputs.
- `runtime/scripts/*.py` with one task-specific mock per service intent.
- `runtime/manifest.yaml` matching the ServiceFlowIR control-flow graph.
- `gold/assertions.yaml` with at least one nominal G6 assertion and any branch-specific assertions.
- generated `argo/workflow.yaml`, `argo/workflow_bundle.yaml`, and optional CronWorkflow resources.
- `validation/report.json` with G0-G6 pass.

## Semantic Hardening Checklist

- Verify no Frozen-60 files were modified.
- Verify every source step is accounted for as `service`, `orchestration`, `noop`, or `unresolvable`.
- Prefer specific service descriptors; add a versioned catalog extension only when the existing catalogue cannot represent the source contract.
- Keep event/checkpoint/window cases bounded batch; do not claim true streaming semantics.
- Candidate sets must contain one gold service plus 2-5 meaningful distractors.
- Run compile and G0-G6 validation before moving to the next batch.
