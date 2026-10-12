# Extension-50 Batch 04

This batch is processed as a complete benchmark-generation unit: source review, catalogue-gap decisions, ServiceFlowIR, gold bindings, candidate labels, artifact mappings, fixtures, mock scripts, Argo output, G0-G6 validation, semantic hardening, and independent adjudication notes.

## Pipelines

| # | Pipeline | Track | Domain | Topology | Complexity | Steps |
|---:|---|---|---|---|---|---:|
| 16 | `support_profile_context_join` | `api_json_table_fusion` | Marketing/Customer Operations | `fan_in` | `medium` | 7 |
| 17 | `building_energy_window_aggregation` | `time_series_sensor_window` | Environmental/Energy | `windowed_batch` | `simple` | 6 |
| 18 | `environmental_sensor_anomaly_batch` | `time_series_sensor_window` | Environmental/Energy | `windowed_batch` | `medium` | 7 |
| 19 | `manufacturing_telemetry_quality_scoring` | `time_series_sensor_window` | Supply Chain/Manufacturing | `fan_out` | `medium` | 7 |
| 20 | `hospital_occupancy_window_forecast_prep` | `time_series_sensor_window` | Healthcare/Public Health | `fan_in` | `complex` | 10 |

## Batch Commands

```bash
python3 scripts/run_extension_benchmark.py --batch 4 --phase bootstrap
python3 scripts/author_extension_batch_04.py
python3 scripts/run_extension_benchmark.py --batch 4 --phase compile
python3 scripts/run_extension_benchmark.py --batch 4 --phase validate
python3 scripts/run_extension_benchmark.py --batch 4 --phase report
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
