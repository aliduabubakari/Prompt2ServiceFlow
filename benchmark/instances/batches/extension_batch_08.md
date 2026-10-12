# Extension-50 Batch 08

This batch is processed as a complete benchmark-generation unit: source review, catalogue-gap decisions, ServiceFlowIR, gold bindings, candidate labels, artifact mappings, fixtures, mock scripts, Argo output, G0-G6 validation, semantic hardening, and independent adjudication notes.

## Pipelines

| # | Pipeline | Track | Domain | Topology | Complexity | Steps |
|---:|---|---|---|---|---|---:|
| 36 | `disaster_response_data_fusion` | `complex_mixed_domain` | Public Sector/Geospatial | `fan_out_fan_in` | `very_complex` | 13 |
| 37 | `smart_city_incident_routing` | `complex_mixed_domain` | Public Sector/Geospatial | `fan_out_fan_in` | `complex` | 10 |
| 38 | `supply_chain_disruption_triage` | `complex_mixed_domain` | Supply Chain/Manufacturing | `fan_out_fan_in` | `complex` | 10 |
| 39 | `research_data_lake_publication_gate` | `complex_mixed_domain` | Science/Biotechnology | `branch_gate` | `very_complex` | 13 |
| 40 | `public_benefits_case_review_notification` | `complex_mixed_domain` | Public Sector/Geospatial | `branch_gate` | `complex` | 10 |

## Batch Commands

```bash
python3 scripts/run_extension_benchmark.py --batch 8 --phase bootstrap
python3 scripts/author_extension_batch_08.py
python3 scripts/run_extension_benchmark.py --batch 8 --phase compile
python3 scripts/run_extension_benchmark.py --batch 8 --phase validate
python3 scripts/run_extension_benchmark.py --batch 8 --phase report
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
