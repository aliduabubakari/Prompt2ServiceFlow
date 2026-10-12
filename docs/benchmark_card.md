# ServiceComposeBench-ETL Benchmark Card

Status: two-instance local vertical slice implemented

## Source

- Dataset: Structured ETL and Data-Preparation Pipeline Descriptions for LLM
  Workflow Generation Studies
- DOI: https://doi.org/10.5281/zenodo.20377524
- Version: v1.0.0
- License: CC BY 4.0

## Intended Task

The benchmark will evaluate service identification, service discovery and
binding, contract closure, deterministic Argo compilation, mock execution, and
semantic assertions from natural-language pipeline descriptions.

## Current Scope

The source layer contains 40 main descriptions and 20 held-out validation
descriptions. The validation descriptions are treated as an
ambiguity/robustness track because their step objectives are intentionally
generic.

The first two main instances, AirVisual and Data Quality Gate, now include
reviewable ServiceFlowIR, hidden gold bindings and artifact maps, public
candidate sets, contracts, deterministic fixtures, task-specific Python mocks,
generated Argo resources, and local G0-G6 reports. Their Workflow resources
pass `argo lint --offline`. Cluster-backed execution remains pending.

## Leakage Boundary

Published descriptions and model-visible service candidates are public inputs.
Companion PipelineSpecs, gold bindings, candidate labels, fixtures, assertions,
and reviewer adjudication records are hidden evaluation evidence.
