# Catalogue Generation

The catalogue generator uses GPT-5.5 through the Responses API, with exactly
one active pipeline in each request. It does not ask the model to write final
snapshot files directly.

## Why Two Phases

1. `required` accounts for every source step and builds the reusable required
   service registry.
2. The required registry is reviewed.
3. `distractors` creates capability-overlapping alternatives and private
   candidate relationship labels.
4. `curate` globally namespaces candidate sets and adds the bounded reviewed
   supplemental distractor pool.
5. `finalize` validates descriptors and writes an immutable catalogue snapshot.

Separating the phases prevents distractor ideas from changing the definition
of the required services and keeps answer labels out of model-visible
descriptors.

## Request Context

Every request contains:

- stable catalogue-architecture instructions;
- a compact index of all pipelines selected for the run;
- the current reusable service registry;
- the complete public description for the active pipeline;
- the complete internal companion specification for the active pipeline.

Sending all 742,000 source characters in every request would repeat the corpus
60 times. The compact index preserves corpus-wide awareness while the active
pipeline receives full evidence. The stable prefix is paired with a
phase-and-scope-specific prompt cache key and 24-hour cache retention.

## API Configuration

Defaults are in `config/catalog_generation.yaml`:

```yaml
model: gpt-5.5
reasoning_effort: medium
reasoning_summary: auto
verbosity: low
max_output_tokens: 30000
temperature: null
store: false
```

The Responses API parameter is `max_output_tokens`; `max_completion_tokens`
belongs to other API surfaces. The 30,000-token allowance includes visible
output and reasoning tokens. OpenAI recommends initially reserving at least
25,000 tokens for reasoning and output. Structured Outputs are generated from
Pydantic models and the resulting descriptors are independently validated
against `schemas/service_descriptor.schema.json`.

GPT-5.5 rejects the `temperature` parameter, so it is omitted when the
configuration value is `null`. The field remains optional for other models
that support sampling temperature.

`medium` reasoning is used because reasoning tokens count against
`max_output_tokens`. In the AirVisual pilot, both `xhigh` and `high` exhausted
the original 10,000-token allowance before the structured JSON document
completed.
This task benefits more from preserving the output budget for complete
contracts and descriptors than from additional hidden reasoning.

Low output verbosity keeps explanatory strings concise while Structured
Outputs still require every interface, policy, contract, and accounting field.
This helps preserve budget for complex multi-service pipelines such as Data
Quality Gate and `global_dag`.

The script loads `OPENAI_API_KEY` from `.env` only when `--execute` is present.
It never prints the key.

## Dry Run

Render prompts without making paid requests:

```bash
python3 scripts/generate_service_catalog.py required --limit 2
```

Prompts and run metadata are written beneath:

```text
runs/catalog_generation/gpt55-catalog-v001/
```

## Execute

The recommended runner invokes one pipeline per process, writes individual
logs, retries bounded failures, and safely resumes completed work:

```bash
scripts/run_catalog_pipelines.sh --execute
```

After reviewing `registry/required/`, run:

```bash
scripts/run_catalog_pipelines.sh --phase distractors --execute
```

After all 40 distractor responses complete, apply the deterministic release
curation policy:

```bash
python3 scripts/generate_service_catalog.py curate
```

This command makes no API calls. It installs eight reviewed supplemental
services, adds at most one suitable supplemental relation per candidate set,
globally namespaces candidate-set IDs, and writes
`reports/catalog_curation.json`. See `docs/catalog_curation_policy.md`.

The runner stops at the first pipeline that exhausts its retries. Use
`--continue-on-error` only when it is acceptable to continue making paid calls
after a failure. Useful controls include:

```bash
scripts/run_catalog_pipelines.sh \
  --start-at main:some_pipeline \
  --limit 5 \
  --execute
```

Without `--execute`, the runner renders prompts but does not call OpenAI.
Per-pipeline and summary logs are stored under
`runs/catalog_generation/<run-id>/logs/<phase>/`.

The Python command remains available for targeted single-pipeline work:

```bash
python3 scripts/generate_service_catalog.py required \
  --pipeline main:airvisual_pipeline_lat_long_v1 \
  --execute
```

Inspect progress at any point:

```bash
python3 scripts/generate_service_catalog.py status
```

Finalize only after every selected pipeline has both responses and `curate`
has completed:

```bash
python3 scripts/generate_service_catalog.py finalize
```

The visible snapshot is written to
`benchmark/catalog/snapshots/<version>/`. Private candidate labels and the
duplicate-capability review report are written to
`benchmark/catalog/review/<version>/`.

Runs are resumable. Completed response files are skipped. Every paid response
is also retained under `attempts/` before local semantic validation so failed
post-processing remains auditable.

## Main Versus Validation Split

The research-safe default uses only the 40 `main` pipelines to construct the
catalogue. Using the 20 prospective validation pipelines to add services can
leak their capability distribution into benchmark design.

Recommended procedure:

1. Generate and review the catalogue from `main`.
2. Freeze a draft snapshot.
3. Map validation pipelines to that snapshot as a coverage audit.
4. Record missing capabilities as catalogue gaps or approve additions through
   an explicit change process.

For a deliberately all-60 catalogue build, add `validation` to `splits` in a
new configuration, or use both explicit CLI overrides:

```bash
scripts/run_catalog_pipelines.sh \
  --scope all \
  --run-id gpt55-catalog-all60-v001
```

Use the same split arguments and run ID for the distractor and finalize phases.
Give the resulting snapshot a distinct catalogue version and record the choice
in the benchmark methodology.
