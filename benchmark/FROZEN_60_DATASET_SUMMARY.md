# Prompt2ServiceFlow Benchmark Dataset Summary

Snapshot date: 2026-06-27  
Current benchmark size: 110 pipeline instances  
Frozen baseline: 60 pipeline instances  
Extension set: 50 pipeline instances  
Frozen catalogue snapshot: `benchmark/catalog/snapshots/0.2.3`  
Current catalogue snapshot: `benchmark/catalog/snapshots/0.3.9`  
Status: locally complete for ServiceFlowIR, service bindings, artifact
mappings, candidate sets, candidate labels, deterministic mock runtimes,
fixtures, Argo manifests, workflow bundles, and G0-G6 validation reports.

This document is the main internal reference for reporting the
Prompt2ServiceFlow benchmark. It extends the earlier Frozen-60 report with the
new Extension-50 set. The intended paper framing is now:

```text
Frozen-60 baseline + Extension-50 diversity expansion = Prompt2ServiceFlow-110
```

The Frozen-60 subset remains the historically frozen benchmark snapshot used
for the original main work. The Extension-50 subset is a curated diversity
expansion that adds multimodal, API/table fusion, bounded time-series,
checkpointed event-batch, policy/privacy/human-review, complex mixed-domain,
and AI/LLM/NLP workflows. Unless a paper experiment explicitly studies only the
Frozen-60 baseline, new benchmark reporting should use the complete 110
instances and catalogue snapshot `0.3.9`.

All counts in this document were computed from repository artifacts:

- `benchmark/manifest.jsonl`
- `benchmark/instances/{main,validation,extension}`
- `benchmark/source/extension_v1`
- `benchmark/catalog/snapshots`
- per-instance `gold/serviceflow.yaml`
- per-instance `gold/candidate_labels.yaml`
- per-instance `candidates/candidate_sets.yaml`
- per-instance `runtime/manifest.yaml`
- per-instance `argo/*`
- per-instance `validation/report.json`

## Executive Summary

Prompt2ServiceFlow is a benchmark for evaluating whether an LLM system can turn
a natural-language or semi-structured pipeline description into a contract-bound
service composition and then into an Argo-projectable workflow.

The benchmark is not only a set of prompts. Each pipeline instance contains:

1. A model-visible pipeline description and/or source-derived internal spec.
2. Gold ServiceFlowIR.
3. Gold service bindings.
4. Gold artifact mappings.
5. Public candidate service sets.
6. Private candidate labels.
7. Runtime mock scripts and fixtures.
8. Argo `Workflow` output.
9. A deployable workflow bundle containing the workflow and supporting
   Kubernetes resources.
10. G0-G6 validation reports.

The current 110-instance benchmark contains:

| Dimension | Count |
|---|---:|
| Pipeline instances | 110 |
| Frozen baseline instances | 60 |
| Extension instances | 50 |
| Service intents | 819 |
| Gold service bindings | 819 |
| Artifacts in ServiceFlowIR | 1,829 |
| Control-flow edges in ServiceFlowIR | 869 |
| Candidate sets | 716 |
| Candidate-service relations | 3,060 |
| Gold candidate relations | 716 |
| Distractor candidate relations | 2,344 |
| Unique gold-bound services | 483 |
| Final catalogue services | 527 |
| Runtime mock scripts | 701 |
| Argo workflow manifests | 110 |
| Argo workflow bundles | 110 |
| G0-G6 passing instances | 110 |

The Extension-50 materially changes the benchmark rather than merely making it
larger. The Frozen-60 has a median of 5 service intents per pipeline; the
Extension-50 has a median of 10. The final catalogue grows from 225 services in
the frozen baseline to 527 services in the complete benchmark. The extension
also introduces non-tabular inputs, AI/RAG pipelines, policy review patterns,
checkpointed event batches, and richer fan-in/fan-out compositions.

## Source Dataset and Provenance

The original public source for the Frozen-60 description corpus is:

Alidu, A., Ciavotta, M., & Flavio, D. P. (2026). *Structured ETL and
Data-Preparation Pipeline Descriptions for LLM Workflow Generation Studies*
(v1.0.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.20377524

The Frozen-60 uses the 40 main and 20 validation descriptions from that source.
The Extension-50 is a synthetic, provenance-marked expansion developed inside
this repository under `benchmark/source/extension_v1`. It was designed to
improve benchmark diversity without mutating the Frozen-60 baseline.

| Split | Instances | Source type | Role |
|---|---:|---|---|
| `main` | 40 | Original + synthetic descriptions from the source corpus | Development/evaluation baseline |
| `validation` | 20 | Prospective low-information validation descriptions | Locked holdout baseline |
| `extension` | 50 | SyntheticExtension, provenance-marked | Diversity/generalization expansion |
| Total | 110 | Mixed | Full benchmark |

Source-type distribution:

| Source type | Count |
|---|---:|
| `SyntheticExtension` | 50 |
| `Synthetic` | 25 |
| `ValidationSynthetic` | 20 |
| `Original` | 15 |
| Total | 110 |

## Benchmark Scope and Scientific Justification

The benchmark is designed for prompt-to-service-composition research. The
target task is:

```text
natural-language pipeline requirement
  -> abstract service-intent decomposition
  -> closed-world service discovery
  -> concrete service binding
  -> artifact and contract mapping
  -> ServiceFlowIR
  -> deterministic Argo Workflow projection
  -> local semantic and structural validation
```

The benchmark is scientifically justified by five design choices.

First, it targets a specific missing evaluation surface. Existing workflow
benchmarks often evaluate scheduling, graph execution, process-model generation,
or general API use. Prompt2ServiceFlow instead evaluates the middle layer that
is crucial for LLM-based automation systems: selecting and binding reusable
services from a closed catalogue while preserving artifacts, contracts,
policies, and control-flow semantics.

Second, the unit of evaluation is semantically dense. A 110-instance corpus may
look modest if counted as prompts, but it contains 819 gold service bindings,
1,829 artifacts, 869 control-flow edges, and 3,060 candidate-service relations.
Each instance therefore contributes multiple independently checkable semantic
decisions.

Third, the dataset is topology-aware. It includes linear, fan-out, fan-in,
fan-out/fan-in, branch/merge, staged ETL, sensor-gated/windowed, and mixed
workflows. This matters because LLM workflow errors often arise not from
single-step generation but from incorrect dependency preservation, branch
routing, merge semantics, and artifact propagation.

Fourth, the service catalogue is closed-world and versioned. The model is not
allowed to invent an arbitrary service implementation for each pipeline. It
must select from a catalogue with capability-overlapping services and
controlled distractors. This makes the benchmark closer to realistic enterprise
service composition, where a workflow author must bind to existing governed
services.

Fifth, the benchmark is execution-honest. The repository includes deterministic
mock scripts, fixtures, Argo manifests, and workflow bundles. Local G0-G6
validation is complete for all 110 instances. Full G5 cluster execution and
independent human adjudication are still separate qualification steps rather
than silently assumed results.

## Relationship Between Frozen-60 and Extension-50

The Frozen-60 is the stable baseline. It should still be used when comparing
against early Prompt2ServiceFlow experiments, especially those conducted before
the diversity expansion.

The Extension-50 is the recommended expansion for new experiments. It improves
three aspects of the benchmark:

1. **Input modality diversity.** The Frozen-60 is mostly batch data-preparation
   and ETL-like workflows. The Extension-50 adds PDF, image, text, JSON,
   JSONL, GeoJSON, time-series, and hybrid multimodal inputs.
2. **Service-binding diversity.** The final catalogue grows from 225 to 527
   services, with large additions in extraction, transformation, publishing,
   quality checking, domain adaptation, aggregation, integration, and AI/RAG
   services.
3. **Workflow complexity.** The Extension-50 increases the median number of
   source steps from 5 to 10 and adds more fan-in, branch/gate, bounded event,
   policy-review, and AI/NLP pipelines.

The two subsets should be reported separately when possible:

| Subset | Instances | Recommended use |
|---|---:|---|
| Frozen-60 | 60 | Baseline comparability, original dataset reporting |
| Extension-50 | 50 | Diversity/generalization, multimodal and AI/NLP stress tests |
| All-110 | 110 | Main current benchmark result |

## Dataset Composition

### Split Distribution

| Split | Instances | Percentage |
|---|---:|---:|
| `main` | 40 | 36.4% |
| `validation` | 20 | 18.2% |
| `extension` | 50 | 45.5% |
| Total | 110 | 100.0% |

### Topology Distribution

Manifest-level topology distribution after normalization:

| Topology | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| Linear | 23 | 22 | 1 |
| Branch/merge | 22 | 9 | 13 |
| Fan-out/fan-in | 18 | 10 | 8 |
| Fan-in | 13 | 0 | 13 |
| Staged ETL | 9 | 4 | 5 |
| Fan-out only | 7 | 4 | 3 |
| Windowed batch | 7 | 0 | 7 |
| Mixed | 6 | 6 | 0 |
| Sensor-gated | 5 | 5 | 0 |
| Total | 110 | 60 | 50 |

ServiceFlowIR-level topology distribution:

| ServiceFlowIR topology | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| `fan_out_fan_in` | 31 | 10 | 21 |
| `linear` | 23 | 22 | 1 |
| `branch_merge` | 22 | 9 | 13 |
| `sensor_gated` | 12 | 5 | 7 |
| `staged_etl` | 9 | 4 | 5 |
| `fan_out` | 7 | 4 | 3 |
| `mixed` | 6 | 6 | 0 |
| Total | 110 | 60 | 50 |

### Complexity Distribution

| Complexity | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| Simple | 18 | 10 | 8 |
| Moderate | 34 | 20 | 14 |
| Complex | 35 | 17 | 18 |
| Very complex | 23 | 13 | 10 |
| Total | 110 | 60 | 50 |

The Validation-20 split remains deliberately balanced by complexity:

| Complexity | Validation-20 |
|---|---:|
| Simple | 5 |
| Moderate | 5 |
| Complex | 5 |
| Very complex | 5 |
| Total | 20 |

### Information Sufficiency

| Information sufficiency | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| High | 81 | 31 | 50 |
| Medium | 9 | 9 | 0 |
| Low | 20 | 20 | 0 |
| Total | 110 | 60 | 50 |

The Validation-20 remains the intentionally low-information holdout. The
Extension-50 is high-information because it was created as a structured
diversity expansion with explicit topology, modality, and domain targets.

### Execution Model

| Execution model | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| Batch | 59 | 59 | 0 |
| Bounded batch | 50 | 0 | 50 |
| Hybrid | 1 | 1 | 0 |
| Total | 110 | 60 | 50 |

The Extension-50 deliberately avoids true streaming runtime requirements. Its
event and time-series examples are bounded-batch or checkpointed-batch designs,
which preserves compatibility with deterministic local validation and Argo
dry-run workflows.

## Extension-50 Design

The Extension-50 was designed to improve diversity without mutating the
Frozen-60. It contains seven tracks:

| Extension track | Instances | Purpose |
|---|---:|---|
| `image_document_multimodal` | 10 | Adds first-class non-tabular inputs such as image, PDF, document, and OCR-like flows. |
| `api_json_table_fusion` | 6 | Strengthens multi-source API/JSON/table service composition. |
| `time_series_sensor_window` | 6 | Adds bounded time-series, sensor, and windowed analysis workflows. |
| `event_checkpoint_windowed_batch` | 8 | Adds checkpointed event-batch and replay-style pipelines without true streaming runtime. |
| `policy_privacy_human_review` | 5 | Stresses PHI/PII, redaction, governance, review routing, and audit evidence. |
| `complex_mixed_domain` | 5 | Adds fan-in/fan-out, branch/gate, cross-domain fusion, and stakeholder packet workflows. |
| `ai_llm_nlp` | 10 | Adds PDF ingestion, chunking, embedding, vector index, retrieval, structured extraction, summarization, and RAG-like pipelines. |
| Total | 50 | Diversity/generalization expansion. |

### Extension Batches

| Batch | Track focus | Pipelines | Steps | Edges |
|---:|---|---:|---:|---:|
| 1 | Image/document multimodal | 5 | 39 | 39 |
| 2 | Image/document multimodal | 5 | 41 | 41 |
| 3 | API/JSON/table fusion | 5 | 39 | 35 |
| 4 | API/table fusion + time-series | 5 | 37 | 34 |
| 5 | Time-series + event/checkpoint | 5 | 37 | 33 |
| 6 | Event/checkpoint | 5 | 36 | 32 |
| 7 | Policy/privacy/human-review | 5 | 50 | 48 |
| 8 | Complex mixed-domain | 5 | 56 | 59 |
| 9 | AI/LLM/NLP | 5 | 62 | 62 |
| 10 | AI/LLM/NLP | 5 | 59 | 58 |
| Total |  | 50 | 456 | 441 |

### Extension Input Modalities

Input modalities are multi-label. A pipeline may contribute more than one
modality.

| Input modality | Uses |
|---|---:|
| `table` | 41 |
| `json` | 35 |
| `text` | 19 |
| `pdf` | 15 |
| `image` | 13 |
| `time_series` | 7 |
| `jsonl` | 7 |
| `geojson` | 3 |

### Extension Output Modalities

Output modalities are multi-label.

| Output modality | Uses |
|---|---:|
| `table` | 26 |
| `json` | 16 |
| `audit_log` | 16 |
| `review_packet` | 15 |
| `checkpoint_manifest` | 6 |
| `status` | 5 |
| `exception_report` | 5 |
| `alert_digest` | 5 |
| `summary` | 5 |
| `geojson` | 4 |
| `risk_report` | 4 |
| `quality_report` | 4 |
| `feature_manifest` | 3 |
| `notification` | 3 |
| `redacted_text` | 2 |
| `vector_index` | 2 |
| Other singleton outputs | 14 |

Singleton outputs include `pdf`, `redacted_pdf`, `quarantine_report`,
`redacted_table`, `briefing_packet`, `work_order`, `publication_manifest`,
`manifest`, `routing_decision`, `listing_summary`, `answer_pack`,
`evaluation_report`, `control_mapping`, and `action_register`.

### Extension Domains

| Domain | Instances |
|---|---:|
| Environmental/Energy | 6 |
| Finance/Risk | 6 |
| Legal/Compliance | 6 |
| Healthcare/Public Health | 5 |
| Public Sector/Geospatial | 5 |
| Supply Chain/Manufacturing | 5 |
| AI Platform Operations | 5 |
| Retail/E-commerce | 4 |
| Marketing/Customer Operations | 4 |
| Education/Research | 2 |
| Science/Biotechnology | 2 |
| Total | 50 |

## Source-Description Size

These counts come from `benchmark/manifest.jsonl`.

| Metric | All-110 sum | All-110 min | All-110 median | All-110 mean | All-110 max |
|---|---:|---:|---:|---:|---:|
| Source steps | 831 | 1 | 7.0 | 7.55 | 24 |
| Source edges | 825 | 0 | 6.0 | 7.50 | 39 |
| Description steps | 831 | 1 | 7.0 | 7.55 | 24 |
| Description edges | 825 | 0 | 6.0 | 7.50 | 39 |
| Unknown mechanism count | 21 | 0 | 0.0 | 0.19 | 6 |
| Generic objective count | 120 | 0 | 0.0 | 1.09 | 12 |

Comparison by subset:

| Metric | Frozen-60 sum | Frozen-60 median | Frozen-60 mean | Extension-50 sum | Extension-50 median | Extension-50 mean |
|---|---:|---:|---:|---:|---:|---:|
| Source steps | 375 | 5.0 | 6.25 | 456 | 10.0 | 9.12 |
| Source edges | 384 | 4.0 | 6.40 | 441 | 9.0 | 8.82 |
| Description steps | 375 | 5.0 | 6.25 | 456 | 10.0 | 9.12 |
| Description edges | 384 | 4.0 | 6.40 | 441 | 9.0 | 8.82 |
| Unknown mechanisms | 21 | 0.0 | 0.35 | 0 | 0.0 | 0.00 |
| Generic objectives | 120 | 0.0 | 2.00 | 0 | 0.0 | 0.00 |

## ServiceFlowIR Statistics

These counts come from `gold/serviceflow.yaml`.

| Metric | All-110 sum | Min | Median | Mean | Max |
|---|---:|---:|---:|---:|---:|
| Service intents | 819 | 1 | 7.0 | 7.45 | 22 |
| Service bindings | 819 | 1 | 7.0 | 7.45 | 22 |
| Artifacts | 1,829 | 2 | 15.0 | 16.63 | 49 |
| Control-flow edges | 869 | 0 | 6.0 | 7.90 | 100 |
| Parallel groups | 53 | 0 | 0.0 | 0.48 | 2 |
| Branches | 27 | 0 | 0.0 | 0.25 | 1 |
| Gates/sensors | 27 | 0 | 0.0 | 0.25 | 1 |

Subset comparison:

| Metric | Frozen-60 sum | Frozen-60 median | Frozen-60 mean | Extension-50 sum | Extension-50 median | Extension-50 mean |
|---|---:|---:|---:|---:|---:|---:|
| Service intents | 363 | 5.0 | 6.05 | 456 | 10.0 | 9.12 |
| Service bindings | 363 | 5.0 | 6.05 | 456 | 10.0 | 9.12 |
| Artifacts | 867 | 12.0 | 14.45 | 962 | 21.0 | 19.24 |
| Control-flow edges | 428 | 4.0 | 7.13 | 441 | 9.0 | 8.82 |
| Parallel groups | 29 | 0.0 | 0.48 | 24 | 0.0 | 0.48 |
| Branches | 14 | 0.0 | 0.23 | 13 | 0.0 | 0.26 |
| Gates/sensors | 14 | 0.0 | 0.23 | 13 | 0.0 | 0.26 |

Control-flow feature coverage:

| Feature | All-110 structures | All-110 instances with feature | Frozen-60 instances | Extension-50 instances |
|---|---:|---:|---:|---:|
| Parallel groups | 53 | 46 | 22 | 24 |
| Branches | 27 | 27 | 14 | 13 |
| Gates/sensors | 27 | 27 | 14 | 13 |

Schedule representation:

| Schedule type | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| `manual` | 72 | 22 | 50 |
| `cron` | 38 | 38 | 0 |
| Total | 110 | 60 | 50 |

## Service Catalogue Evolution

The Frozen-60 baseline ends at catalogue snapshot `0.2.3`. The Extension-50
continues the same versioned catalogue to `0.3.9`.

| Snapshot | Services | New vs previous | Role |
|---|---:|---:|---|
| `0.1.0` | 137 | 137 | Initial generated/curated Main-40 catalogue |
| `0.1.1` | 138 | 1 | Main-40 semantic-hardening extension |
| `0.2.0` | 148 | 10 | Validation batch 01 extension |
| `0.2.1` | 162 | 14 | Validation batch 02 extension |
| `0.2.2` | 190 | 28 | Validation batch 03 extension |
| `0.2.3` | 225 | 35 | Final Frozen-60 catalogue |
| `0.3.0` | 241 | 16 | Extension batch 01 multimodal services |
| `0.3.1` | 260 | 19 | Extension batch 02 multimodal/fan-in services |
| `0.3.2` | 279 | 19 | Extension batch 03 API/table fusion services |
| `0.3.3` | 293 | 14 | Extension batch 04 time-series/window services |
| `0.3.4` | 305 | 12 | Extension batch 05 checkpoint/event services |
| `0.3.5` | 335 | 30 | Extension batch 06 event/checkpoint/audit services |
| `0.3.6` | 385 | 50 | Extension batch 07 policy/privacy/review services |
| `0.3.7` | 436 | 51 | Extension batch 08 complex mixed-domain services |
| `0.3.8` | 483 | 47 | Extension batch 09 AI/RAG/NLP services |
| `0.3.9` | 527 | 44 | Final Extension-50 AI/NLP services |

### Final Catalogue Category Distribution

Snapshot `0.3.9`:

| Service category | Services |
|---|---:|
| Extractor | 106 |
| Transformer | 88 |
| Publisher | 69 |
| QualityCheck | 47 |
| DomainAdapter | 44 |
| Loader | 35 |
| Aggregator | 27 |
| ScoringService | 26 |
| Integrator | 20 |
| Notifier | 14 |
| Reconciler | 13 |
| ReportGenerator | 13 |
| Maintenance | 9 |
| Sensor | 6 |
| ExternalWorkflowAdapter | 5 |
| DataProfiler | 4 |
| PrivacyService | 1 |
| Total | 527 |

Frozen snapshot `0.2.3` for comparison:

| Service category | Services |
|---|---:|
| Extractor | 38 |
| Transformer | 37 |
| Loader | 23 |
| Publisher | 18 |
| DomainAdapter | 15 |
| Notifier | 14 |
| ScoringService | 14 |
| ReportGenerator | 13 |
| QualityCheck | 11 |
| Maintenance | 9 |
| Aggregator | 6 |
| Reconciler | 6 |
| Sensor | 6 |
| Integrator | 5 |
| ExternalWorkflowAdapter | 5 |
| DataProfiler | 4 |
| PrivacyService | 1 |
| Total | 225 |

### Catalogue Lifecycle and Policy Distribution

Final snapshot `0.3.9` lifecycle:

| Lifecycle status | Services |
|---|---:|
| `active` | 521 |
| `deprecated` | 3 |
| `experimental` | 3 |
| Total | 527 |

Final snapshot `0.3.9` provenance:

| Provenance origin | Services |
|---|---:|
| `curated` | 397 |
| `generated` | 129 |
| `curated_extension` | 1 |
| Total | 527 |

Final snapshot `0.3.9` policy distribution:

| Policy field | Value | Services |
|---|---|---:|
| `network_access` | `forbidden` | 417 |
| `network_access` | `required` | 104 |
| `network_access` | `optional` | 6 |
| `secret_access` | `forbidden` | 421 |
| `secret_access` | `optional` | 67 |
| `secret_access` | `required` | 39 |

This policy distribution is important for the paper: the benchmark does not
merely ask models to choose semantically similar tools. It also asks them to
avoid tools that violate runtime, policy, target-system, or contract
constraints.

## Gold Service-Binding Coverage

Across all 110 ServiceFlowIR files:

| Binding metric | Count |
|---|---:|
| Total service bindings | 819 |
| Unique gold-bound services | 483 |
| Final catalogue services | 527 |
| Catalogue services used at least once as gold | 483 |
| Catalogue services not gold-bound in current instances | 44 |

Gold-bound service categories:

| Category | All-110 bindings | Frozen-60 bindings | Extension-50 bindings |
|---|---:|---:|---:|
| Extractor | 200 | 95 | 105 |
| Transformer | 152 | 58 | 94 |
| Publisher | 101 | 22 | 79 |
| QualityCheck | 66 | 12 | 54 |
| Loader | 51 | 34 | 17 |
| DomainAdapter | 42 | 16 | 26 |
| Aggregator | 38 | 6 | 32 |
| ScoringService | 32 | 20 | 12 |
| Maintenance | 28 | 28 | 0 |
| Integrator | 26 | 5 | 21 |
| Reconciler | 25 | 9 | 16 |
| Sensor | 17 | 17 | 0 |
| ReportGenerator | 14 | 14 | 0 |
| Notifier | 14 | 14 | 0 |
| ExternalWorkflowAdapter | 8 | 8 | 0 |
| DataProfiler | 4 | 4 | 0 |
| PrivacyService | 1 | 1 | 0 |
| Total | 819 | 363 | 456 |

Most frequent gold-bound services in All-110:

| Service | Gold bindings |
|---|---:|
| `http_api_request_artifact_extractor` | 19 |
| `airflow_metadata_retention_cleaner` | 11 |
| `temporary_resource_cleanup` | 10 |
| `semantic_document_chunker` | 10 |
| `deterministic_text_embedding_generator` | 10 |
| `multimodal_output_bundle_publisher` | 10 |
| `multimodal_source_bundle_ingestor` | 9 |
| `multimodal_source_contract_validator` | 9 |
| `file_location_availability_sensor` | 8 |
| `fixture_vector_index_writer` | 7 |
| `grounding_context_retriever` | 7 |
| `tabular_dataset_database_loader` | 6 |
| `database_csv_snapshot_exporter` | 6 |
| `structured_json_to_csv_exporter` | 6 |
| `csv_tabular_schema_validating_loader` | 6 |
| `timeseries_output_bundle_publisher` | 6 |
| `api_table_output_bundle_publisher` | 6 |
| `visual_document_feature_extractor` | 6 |
| `multimodal_reference_metadata_joiner` | 6 |
| `http_json_request_extractor` | 5 |

## Candidate Sets and Distractors

Candidate sets define the service-selection subtask. Public candidate sets live
in `candidates/candidate_sets.yaml`; private labels live in
`gold/candidate_labels.yaml`.

| Candidate metric | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| Candidate sets | 716 | 260 | 456 |
| Candidate-service relations | 3,060 | 1,236 | 1,824 |
| Average candidates per set | 4.27 | 4.75 | 4.00 |
| Gold candidate relations | 716 | 260 | 456 |
| Distractor candidate relations | 2,344 | 976 | 1,368 |
| Unique gold services | 483 | 205 | 278 |
| Unique distractor services | 169 | 134 | 41 |

Candidate-set size distribution:

| Candidates per set | Sets |
|---|---:|
| 3 | 100 |
| 4 | 458 |
| 5 | 20 |
| 6 | 138 |
| Total | 716 |

The Main-40 candidate sets are denser, with many six-candidate sets. The
Validation-20 uses a consistent three-candidate structure. The Extension-50 uses
a four-candidate structure for nearly all sets: one gold service and three
controlled distractors.

### Candidate Label Distribution

| Label | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| `gold` | 716 | 260 | 456 |
| `semantic_mismatch` | 710 | 254 | 456 |
| `format_mismatch` | 552 | 96 | 456 |
| `contract_mismatch` | 518 | 120 | 398 |
| `generic_escape_hatch` | 243 | 185 | 58 |
| `target_mismatch` | 163 | 163 | 0 |
| `missing_required_output` | 85 | 85 | 0 |
| `policy_incompatible` | 40 | 40 | 0 |
| `deprecated_or_incompatible` | 33 | 33 | 0 |
| Total candidate-service relations | 3,060 | 1,236 | 1,824 |

Most frequent distractor services in All-110:

| Distractor service | Uses |
|---|---:|
| `reviewed_domain_adapter` | 277 |
| `csv_to_structured_json_standardizer` | 111 |
| `json_field_projection_transformer` | 62 |
| `dataset_quarantine_zone_writer` | 57 |
| `image_cdn_batch_downloader` | 47 |
| `temporary_resource_cleanup` | 45 |
| `document_feature_validation_quality_check` | 45 |
| `reviewed_python_udf_transformer` | 43 |
| `tabular_dataset_database_loader` | 40 |
| `http_json_request_extractor` | 39 |
| `iot_anomaly_feature_calculator` | 39 |
| `event_record_cleaner` | 39 |
| `generic_llm_prompt_runner` | 34 |
| `embedding_index_manifest_archiver` | 33 |
| `rag_index_without_answer_generator` | 33 |
| `keyword_only_document_searcher` | 32 |
| `geojson_format_converter_only` | 32 |
| `invoice_ocr_without_reconciliation` | 31 |
| `chunk_count_quality_checker` | 30 |
| `generic_control_mapping_table_joiner` | 30 |
| `notification_only_publisher` | 30 |
| `audit_log_append_only_writer` | 29 |
| `uncontextualized_summary_generator` | 29 |
| `image_caption_only_generator` | 29 |
| `single_source_priority_ranker` | 29 |

The distractors are capability-overlapping by design. They test whether a model
can distinguish the exact service contract, required output, target system,
artifact format, policy constraint, and workflow role from merely similar
service descriptions.

## Runtime and Argo Outputs

Each instance includes deterministic mock scripts and Argo orchestration
outputs.

| Artifact | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| `gold/serviceflow.yaml` | 110 | 60 | 50 |
| `gold/bindings.yaml` | 110 | 60 | 50 |
| `gold/artifact_mappings.yaml` | 110 | 60 | 50 |
| `gold/candidate_labels.yaml` | 110 | 60 | 50 |
| `gold/assertions.yaml` | 110 | 60 | 50 |
| `candidates/candidate_sets.yaml` | 110 | 60 | 50 |
| `runtime/manifest.yaml` | 110 | 60 | 50 |
| `validation/report.json` | 110 | 60 | 50 |
| `argo/workflow.yaml` | 110 | 60 | 50 |
| `argo/workflow_bundle.yaml` | 110 | 60 | 50 |
| `argo/install_manifest.yaml` | 110 | 60 | 50 |
| `argo/cronworkflow.yaml` | 38 | 38 | 0 |
| `argo/cronworkflow_bundle.yaml` | 38 | 38 | 0 |

Runtime mock scripts:

| Runtime-script metric | All-110 | Frozen-60 | Extension-50 |
|---|---:|---:|---:|
| Total scripts | 701 | 245 | 456 |
| Min scripts per instance | 1 | 1 | 5 |
| Median scripts per instance | 6.0 | 4.0 | 10.0 |
| Mean scripts per instance | 6.37 | 4.08 | 9.12 |
| Max scripts per instance | 13 | 12 | 13 |

The workflow bundle files embed the workflow resource together with supporting
ServiceAccount and ConfigMap resources required for local dry-run and offline
linting. This makes the generated Argo outputs more useful for evaluation than
standalone workflow YAML alone.

## Validation Status

All 110 instances have G0-G6 validation reports with passing status.

| Subset | Instances | G0-G6 status |
|---|---:|---|
| Frozen-60 | 60 | pass |
| Extension-50 | 50 | pass |
| All-110 | 110 | pass |

The validation gates cover schema consistency, service binding consistency,
artifact mapping consistency, candidate-set consistency, runtime mock
availability, Argo generation/lint-style checks, and benchmark packaging
expectations. Full G5 execution on a live Argo cluster is still pending.

## Literature Review and Benchmark Positioning

This section situates Prompt2ServiceFlow relative to adjacent benchmark
traditions. The core argument is not that Prompt2ServiceFlow replaces these
benchmarks. Rather, it fills a gap between service-composition research,
workflow-system benchmarking, and modern LLM tool/workflow benchmarks.

### Automated Web-Service Composition

Classical service-composition research studies how to discover, select, and
compose services from formal descriptions. OWL-S is an important early
reference point because it explicitly targets automatic service discovery,
automatic invocation, and automatic composition using declarative service
semantics. The W3C OWL-S submission describes service properties and
capabilities as machine-interpretable descriptions, including prerequisites,
consequences, service compositions, and data-flow interactions
([OWL-S, W3C Member Submission](https://www.w3.org/submissions/OWL-S/)).

Survey work by Rao and Su frames web-service composition as a problem that
draws from both workflow methods and AI planning. They emphasize that
composition becomes difficult when a single service cannot satisfy a user goal
and services must be selected and integrated across heterogeneous systems
([Rao and Su, 2005](https://www.cs.cmu.edu/~jinghai/papers/survey_rao.pdf)).

The Web Services Challenge line of work provided large synthetic service
repositories for evaluating discovery and composition algorithms. The WSC
2009/2010 datasets scale from hundreds to more than fifteen thousand services
and tens of thousands of concepts, with a focus on semantic compatibility and,
in some variants, QoS-aware composition
([WSC 2009/2010 dataset summary](https://wiki.citius.gal/composit%3Awsc09)).

Prompt2ServiceFlow inherits the closed-world service-composition idea from this
tradition, but differs in several ways:

1. It is prompt-driven and LLM-facing rather than planner-only.
2. Its services are workflow/data-preparation capabilities rather than generic
   semantic-web services.
3. It includes gold artifact mappings, runtime mocks, and Argo projection.
4. It evaluates service binding under capability-overlapping distractors.
5. It uses a versioned service catalogue with policies and invocation metadata.

### Scientific Workflow Benchmarks

Scientific workflow benchmarking focuses heavily on workflow execution,
scheduling, simulation, and resource behavior. WfCommons is a strong modern
example. It provides tools for analyzing workflow executions, producing
synthetic workflow generators, and simulating workflow executions. Its goal is
to help researchers evaluate workflow algorithms and systems using realistic
workflow structures and task characteristics
([Coleman et al., 2022](https://www.osti.gov/biblio/1825792)).

Prompt2ServiceFlow is complementary. WfCommons helps answer questions such as:

- How realistic is a generated workflow graph?
- How should workflow systems be scheduled or simulated?
- How do execution traces and resource profiles behave?

Prompt2ServiceFlow instead asks:

- Did the model infer the right service intents?
- Did it bind each intent to the right service descriptor?
- Did it preserve artifact dependencies?
- Did it choose services that satisfy policies and contracts?
- Can the resulting IR be compiled into Argo resources?

This places Prompt2ServiceFlow upstream of execution-performance benchmarks.
It evaluates semantic composition before cluster-scale scheduling or runtime
optimization.

### LLM Workflow-Generation Benchmarks

Recent LLM workflow-generation benchmarks are closer to Prompt2ServiceFlow.
WorkflowLLM introduces WorkflowBench and trains WorkflowLlama to improve LLM
workflow orchestration. The authors highlight that current LLM-based process
automation is constrained by limited ability to orchestrate complex workflows,
including small action scales and limited generalization to unseen APIs
([WorkflowLLM](https://arxiv.org/html/2411.05451v1)).

Flow-Bench studies conversational generation of enterprise workflows. It uses a
Python intermediate representation and converts that IR into BPMN. Its dataset
includes utterances, prior workflow state, expected sequences, and an API list
with descriptions
([Flow-Bench](https://arxiv.org/html/2505.11646v1)).

WORFBENCH studies agentic workflow generation with graph structures and a
workflow evaluation protocol based on subsequence and subgraph matching. Its
motivation is that existing workflow evaluations may be too holistic,
structurally simple, or limited in scenario coverage
([WORFBENCH](https://zjunlp.github.io/project/WorFBench/)).

Prompt2ServiceFlow is aligned with these efforts but emphasizes a different
object of evaluation:

| Benchmark family | Typical target | Prompt2ServiceFlow difference |
|---|---|---|
| WorkflowBench/WorkflowLLM | General workflow orchestration and API action planning | Adds service descriptors, policies, artifacts, bindings, candidate labels, and Argo projection |
| Flow-Bench | Conversational enterprise workflow generation and BPMN conversion | Focuses on data/service composition with closed-world service binding and runtime artifacts |
| WORFBENCH | Agentic graph workflow generation and graph-matching evaluation | Adds catalogue-grounded service selection, artifact mapping, and deployable workflow manifests |

Prompt2ServiceFlow can therefore be positioned as a service-composition
benchmark for workflow generation, rather than only a graph-generation or
process-model-generation benchmark.

### LLM Tool-Use and API Benchmarks

Tool-use benchmarks evaluate whether LLMs can retrieve, plan, and call tools or
APIs. API-Bank provides a runnable tool-augmented evaluation system with 73 API
tools and 314 annotated tool-use dialogues containing 753 API calls, plus a
larger training set spanning 2,138 APIs and 1,000 domains
([API-Bank, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.187/)).

ToolBench/ToolLLM scales tool-use training and evaluation to 16,464 real-world
RESTful APIs across 49 categories, with automatically generated instructions
and solution-path annotation
([ToolLLM/ToolBench](https://arxiv.org/abs/2307.16789)).

StableToolBench is especially relevant for benchmark methodology. It identifies
evaluation instability in ToolBench due to performance, evaluator, and API
status variability, then introduces caching and simulated APIs to improve
stability
([StableToolBench](https://arxiv.org/html/2403.07714v1)).

Prompt2ServiceFlow borrows two important lessons from tool-use benchmarks:

1. Tool/service selection must be evaluated separately from free-form text
   generation.
2. External side effects must be controlled for reproducibility.

The benchmark differs because its unit of work is not an API call or dialogue.
It is a workflow-level service composition with typed artifacts, dependencies,
candidate distractors, runtime scripts, and Argo output. In that sense,
Prompt2ServiceFlow sits between tool-use benchmarks and workflow-generation
benchmarks.

### Why Prompt2ServiceFlow Is Distinctive

Prompt2ServiceFlow is distinctive for the research community because it
combines several features that are usually separated:

1. **Closed-world service composition.** The model must choose from a
   versioned catalogue rather than invent arbitrary tools.
2. **Gold service bindings.** The benchmark evaluates concrete service
   selection, not only generated natural-language plans.
3. **Artifact-level semantics.** Inputs, outputs, intermediate artifacts, and
   status artifacts are represented explicitly.
4. **Capability-overlapping distractors.** Candidate sets include services that
   are plausible but wrong due to target, contract, format, policy, or output
   mismatches.
5. **Workflow control flow.** Branches, gates, fan-in/fan-out, staged ETL, and
   windowed/checkpointed patterns are represented in ServiceFlowIR.
6. **Runtime and orchestration grounding.** Every instance includes mock
   scripts, fixtures, Argo `Workflow` manifests, and workflow bundles.
7. **Versioned catalogue evolution.** The benchmark records how the service
   catalogue expanded from 137 initial services to 527 final services.
8. **Data-preparation focus.** The workflows are grounded in ETL,
   data-preparation, multimodal preparation, policy review, and AI/RAG-style
   data pipelines, which are common in real enterprise and research workflows.

This makes the benchmark especially useful for studying:

- prompt-to-workflow compilation,
- service discovery and binding,
- contract-aware tool selection,
- artifact-flow reconstruction,
- Argo workflow generation,
- service-catalogue robustness,
- structured-output evaluation,
- LLM failure modes in workflow composition.

## Comparison With Existing Benchmark Families

| Benchmark family | Strength | Gap for Prompt2ServiceFlow research | Prompt2ServiceFlow contribution |
|---|---|---|---|
| OWL-S / WSC service-composition benchmarks | Formal service discovery/composition, large repositories | Not LLM-facing, not data-pipeline-specific, limited modern workflow runtime artifacts | LLM-facing closed-world service composition with ServiceFlowIR and Argo projection |
| WfCommons and scientific workflow benchmarks | Realistic workflow traces, simulation, scheduling, resource analysis | Focuses on execution/scheduling rather than natural-language-to-service binding | Semantic composition benchmark before runtime scheduling |
| BPMN / enterprise workflow generation benchmarks | Business process generation and conversational workflow editing | Often evaluates process graphs or API sequences, not artifact-bound data-service workflows | Data-service composition with artifacts, contracts, and mocks |
| Tool/API benchmarks such as API-Bank and ToolBench | API retrieval, planning, and calling at scale | Tool calls are not enough to evaluate workflow-level dependencies and artifact propagation | Workflow-level service binding with candidate distractors and Argo outputs |
| Agentic workflow benchmarks such as WORFBENCH | Graph workflow generation and graph matching | Graph correctness may not capture exact service contracts, artifacts, policies, or runtime packaging | Contract-grounded service graph with validation gates and deployable manifests |

The paper should avoid saying that Prompt2ServiceFlow is universally "better"
than these benchmarks. A stronger and more accurate claim is that it is more
targeted for service-composition research over data-preparation workflows.

## Recommended Paper Claims

Strong claims supported by the current snapshot:

1. The benchmark contains 110 fully annotated pipeline-composition instances.
2. The benchmark includes a Frozen-60 baseline and an Extension-50 diversity
   expansion.
3. The final service catalogue contains 527 versioned service descriptors.
4. The benchmark includes 819 gold service bindings and 1,829 artifacts.
5. The candidate-selection task contains 716 candidate sets and 3,060
   candidate-service relations.
6. All 110 instances have deterministic local G0-G6 validation passing.
7. Every instance includes Argo workflow output and a deployable workflow
   bundle.
8. The benchmark covers batch data preparation, multimodal inputs,
   checkpointed event batches, policy/privacy review, complex mixed-domain
   fusion, and AI/RAG/NLP workflows.

Claims that should be qualified:

1. **Human gold certification.** Independent human adjudication remains pending.
2. **Production execution.** Full G5 execution on a live Argo/Minikube cluster
   remains pending.
3. **External systems.** External systems are fixture-backed and mocked.
4. **Streaming.** The benchmark includes bounded event/checkpoint/windowed
   batch patterns but intentionally does not claim true streaming runtime
   execution.
5. **Synthetic extension.** The Extension-50 is synthetic and
   provenance-marked; it improves diversity but should be reported separately
   from the original Zenodo-derived Frozen-60.

## Reproducibility Notes

Recommended conventions:

1. Use `benchmark/manifest.jsonl` as the canonical instance manifest.
2. Use `benchmark/catalog/snapshots/0.2.3` for Frozen-60-only experiments.
3. Use `benchmark/catalog/snapshots/0.3.9` for full All-110 experiments.
4. Treat `gold/candidate_labels.yaml` and `benchmark/catalog/review/*` as
   private during service-selection experiments.
5. Treat public `candidates/candidate_sets.yaml` as model-visible input.
6. Keep the Validation-20 holdout locked for prospective validation.
7. Report Extension-50 results separately from Frozen-60 when studying
   generalization.
8. Report local mock validation separately from full cluster execution.
9. Do not claim true streaming execution for bounded event/checkpoint cases.
10. Preserve catalogue snapshot versions when comparing experiments over time.

## Known Limitations

1. Independent human adjudication is pending.
2. Full G5 cluster execution is pending.
3. Extension-50 instances are synthetic and should be identified as such.
4. Candidate-label distributions differ across Main-40, Validation-20, and
   Extension-50.
5. External services are mocked by deterministic scripts and fixtures.
6. The benchmark evaluates workflow-level service composition, not low-level
   performance of individual services.
7. The Argo outputs are generated from ServiceFlowIR and locally validated, but
   not yet evaluated on a live cluster for all 110 instances.

## Paper-Reporting Short Form

Prompt2ServiceFlow-110 contains 110 annotated workflow-composition instances:
40 main instances, 20 locked validation-holdout instances, and 50
provenance-marked diversity-extension instances. The benchmark spans nine
normalized topology classes and four difficulty levels. The final service
catalogue contains 527 versioned service descriptors across 17 service
categories. Across the benchmark, the gold annotations contain 819 service
intents and bindings, 1,829 artifacts, 869 control-flow edges, 53 parallel
groups, 27 branch structures, and 27 gate/sensor structures. The
service-selection benchmark contains 716 candidate sets and 3,060
candidate-service relations, including 716 gold relations and 2,344 distractor
relations. All 110 instances include ServiceFlowIR, gold bindings, artifact
mappings, candidate sets, mock runtime scripts, fixtures, Argo manifests,
workflow bundles, and passing G0-G6 local validation reports.

The benchmark is intentionally scoped as a high-density, contract-grounded
service-composition benchmark rather than a general workflow corpus. Its
scientific value comes from the combination of topology diversity, a controlled
difficulty gradient, a locked low-information validation split, a broad
versioned service catalogue, capability-overlapping distractors, explicit
artifact-flow semantics, and deterministic Argo projection. It complements
existing workflow, BPMN, scientific-workflow, and tool-use benchmarks by
focusing on the missing middle layer: turning sparse pipeline requirements into
service-bound, artifact-consistent, policy-aware, Argo-projectable workflow
specifications.
