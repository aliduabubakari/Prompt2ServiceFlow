# Extension-50 Benchmark Generation Pipeline

Extension-50 is processed as ten batches of five pipelines. The package starts
from `benchmark/source/extension_v1` and must not mutate the Frozen-60 baseline
under `benchmark/instances/main` or `benchmark/instances/validation`.

## Scope

The pipeline produces the complete benchmark artifacts for each Extension-50
instance:

- `source/source_metadata.yaml`
- `gold/serviceflow.yaml`
- `gold/bindings.yaml`
- `gold/artifact_mappings.yaml`
- `candidates/candidate_sets.yaml`
- `gold/candidate_labels.yaml`
- `contracts/artifacts/*.schema.json`
- `fixtures/inputs/*`
- `runtime/scripts/*.py`
- `runtime/manifest.yaml`
- `argo/workflow.yaml`
- `argo/workflow_bundle.yaml`
- optional CronWorkflow resources
- `gold/assertions.yaml`
- `validation/report.json`

## One-Time Setup

Regenerate or refresh the source package only when the Extension-50 source
definitions intentionally change:

```bash
python3 scripts/create_extension_50_sources.py
```

Register the 50 extension rows in the benchmark manifest:

```bash
python3 scripts/run_extension_benchmark.py --phase manifest
```

Check the current state:

```bash
python3 scripts/run_extension_benchmark.py --phase status
```

## Batch Workflow

For batch `N`, run:

```bash
python3 scripts/run_extension_benchmark.py --batch N --phase bootstrap
python3 scripts/run_extension_benchmark.py --batch N --phase plan
```

This creates:

- instance directories under `benchmark/instances/extension/<pipeline_id>/`
- source metadata for each selected pipeline
- a batch plan at `benchmark/instances/batches/extension_batch_NN.md`

Then write the reviewed authoring script:

```bash
scripts/author_extension_batch_NN.py
```

The authoring script is responsible for the gold semantics and should create all
gold, candidate, fixture, mock, and runtime files for that batch. It should also
apply any required catalog extension through a new versioned snapshot. Do not add
services silently to an existing frozen snapshot.

After the authoring script exists:

```bash
python3 scripts/author_extension_batch_NN.py
python3 scripts/run_extension_benchmark.py --batch N --phase compile
python3 scripts/run_extension_benchmark.py --batch N --phase validate
python3 scripts/run_extension_benchmark.py --batch N --phase report
```

Or run the full batch command:

```bash
python3 scripts/run_extension_benchmark.py --batch N --phase batch
```

The full batch command expects `scripts/author_extension_batch_NN.py` to exist.

## Semantic Rules

- Every source step must be explicitly accounted for as `service`,
  `orchestration`, `noop`, or `unresolvable`.
- Use specific service descriptors when possible.
- Add new descriptors through a versioned catalog extension only when the
  existing catalogue cannot represent the source contract.
- Candidate sets must contain exactly one gold service and 2-5 meaningful
  distractors.
- Keep `event_checkpoint_windowed_batch` cases bounded batch. They must not claim
  true streaming runtime semantics.
- Mock scripts must be task-specific enough to support G6 assertions, even when
  the actual external system is fixture-backed.
- G5 remains local deterministic mock execution unless a real Argo/Kubernetes
  environment is available and explicitly reported separately.

## Release Discipline

After each batch:

```bash
python3 scripts/run_extension_benchmark.py --phase status
```

After every two batches, run a broader regression over completed Extension-50
instances. A batch is not complete until compile, local G0-G6 validation, semantic
hardening notes, and independent-adjudication records are present.

