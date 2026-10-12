# Extension-50 Batch 02

This batch is processed as a complete benchmark-generation unit: source review, catalogue-gap decisions, ServiceFlowIR, gold bindings, candidate labels, artifact mappings, fixtures, mock scripts, Argo output, G0-G6 validation, semantic hardening, and independent adjudication notes.

## Pipelines

| # | Pipeline | Track | Domain | Topology | Complexity | Steps |
|---:|---|---|---|---|---|---:|
| 6 | `handwritten_form_digitization` | `image_document_multimodal` | Public Sector/Geospatial | `staged` | `medium` | 7 |
| 7 | `shipping_document_ocr_reconciliation` | `image_document_multimodal` | Supply Chain/Manufacturing | `fan_in` | `complex` | 10 |
| 8 | `floor_plan_asset_extraction` | `image_document_multimodal` | Public Sector/Geospatial | `fan_out_fan_in` | `complex` | 10 |
| 9 | `crop_disease_image_triage` | `image_document_multimodal` | Environmental/Energy | `branch_gate` | `simple` | 7 |
| 10 | `document_image_compliance_packet` | `image_document_multimodal` | Legal/Compliance | `fan_out_fan_in` | `medium` | 7 |

## Batch Commands

```bash
python3 scripts/run_extension_benchmark.py --batch 2 --phase bootstrap
python3 scripts/author_extension_batch_02.py
python3 scripts/run_extension_benchmark.py --batch 2 --phase compile
python3 scripts/run_extension_benchmark.py --batch 2 --phase validate
python3 scripts/run_extension_benchmark.py --batch 2 --phase report
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
