# Benchmark Instance Authoring

Instances are developed in batches of five. A batch is not marked complete until
every pipeline has reviewed gold, deterministic Argo output, mock execution, and
G0-G6 results.

## Instance Contract

Each `benchmark/instances/<split>/<pipeline_id>/` directory contains:

- `source/source_metadata.yaml`: immutable source and provenance references;
- `candidates/candidate_sets.yaml`: model-visible candidate IDs without labels;
- `gold/serviceflow.yaml`: authoritative ServiceFlowIR, bindings, policies, and artifact graph;
- `gold/bindings.yaml`: compact gold intent-to-service projection;
- `gold/artifact_mappings.yaml`: compact port-to-artifact projection;
- `gold/candidate_labels.yaml`: private candidate labels and mismatch rationales;
- `gold/assertions.yaml`: reviewed scenario-specific semantic expectations;
- `contracts/artifacts/`: JSON Schemas for material JSON artifacts;
- `fixtures/inputs/`: small, deterministic, credential-free inputs;
- `runtime/scripts/`: one Python implementation per service intent;
- `runtime/manifest.yaml`: script wiring used by both local execution and Argo compilation;
- `argo/`: generated Workflow, optional CronWorkflow, dependency-only install manifest, and
  deployable Workflow/CronWorkflow bundles;
- `validation/report.json`: G0-G6 results.

## Commands

```bash
python3 scripts/compile_instance.py \
  benchmark/instances/main/airvisual_pipeline_lat_long_v1

python3 scripts/validate_instance.py \
  benchmark/instances/main/airvisual_pipeline_lat_long_v1

make sync-main-candidates
make validate-main
```

The local G5 runner executes every declared scenario in an isolated temporary
workspace. G6 assertions are evaluated against a snapshot of that workspace.
External APIs, databases, storage, and email delivery are represented by fixtures
or filesystem-backed mocks.

## Gate Interpretation

- `G0`: schemas, required files, source checksums, and catalogue checksum;
- `G1`: graph references and complete source-step accounting;
- `G2`: exact service/version resolution against the pinned catalogue;
- `G3`: required ports, parameters, secrets, data types, and network policy closure;
- `G4`: deterministic Argo projection, deployable bundle, ConfigMap-size, and structural checks;
- `G5`: successful execution of all mock scenarios;
- `G6`: reviewed semantic assertions pass for all scenarios.

## Argo Deployment-Readiness Evaluation

Evaluate `argo/workflow.yaml` as the runnable Argo object. When present, evaluate
`argo/cronworkflow.yaml` separately. `workflow_bundle.yaml` and
`cronworkflow_bundle.yaml` are deployable Kubernetes bundles: each combines the
dependency-only install resources with exactly one runnable object, avoiding an
immediate Workflow run and a scheduled CronWorkflow run from one apply.

G4 records ConfigMap payload sizes as a static deployment-readiness check. Argo
static or hydrated dry-run scores are deployment-readiness evidence only; they do
not constitute mock-execution evidence (G5) or cluster-success evidence.

Cluster execution remains a release qualification step. The local G5 runner is
the fast deterministic check used during annotation.

## Deferred Cluster Qualification

The `0.1.0` Main-40 hardening pass intentionally defers Minikube-backed Argo
execution until a dedicated virtual machine is available. Local G0-G6 results,
including offline Argo lint, must not be reported as cluster qualification.
The release checklist must retain cluster execution as an explicit outstanding
item until the pinned Argo environment is installed and exercised.
