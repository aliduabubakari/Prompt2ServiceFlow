# Complete local workflow-family controls

Package candidate: `2.0.0-candidate.2`; audit protocol: `5.0.0`.
Local workflow-plan contract: `2.1.0`.

## What this stage establishes

The prior invocation replay confirmed the output-path correction but did not
execute whole workflows. This stage connects three local operations:

```text
file availability -> validate CSV into structured rows -> export those rows
```

The exporter reads the actual JSON artifact written by the validator. If the
file is unavailable, the public Boolean gate skips validation and export. If
validation fails, export is skipped. No schema-derived output examples,
reference outputs, inferred input files, network calls, or database substitute
are used.

This is a **new v2 mechanism-control family**, not an unchanged reference
workflow from the original 110-pipeline corpus. It deliberately avoids claiming
that a local database substitute validates PostgreSQL, or that an exported
CSV completes an original dashboard, supply-chain, or database-loading task.
Source descriptions, original reference IR, hidden assertions, submitted
scores, paper text, v1 release, and DOI are not changed.

## Declared support and limitations

The local workflow executor supports exact version `1.0.0` of:

- `file_location_availability_sensor`: explicitly declared local fixture
  filesystem profile and `exists` condition only. No SFTP, polling, or retries.
- `csv_tabular_schema_validating_loader`: the already verified deterministic
  header/row/required-column subset; no typed/nullable schema inference.
- `structured_json_to_csv_exporter`: the already verified tabular export subset.

Canonical artifact identity and service-requested output locations retain the
separate namespaces verified in candidate.1. That port-writing component is
reused unchanged; candidate.2 adds workflow scheduling/dataflow and context
rendering rather than changing old candidate code or evidence.

Dependencies come from explicit control edges and actual artifact producers,
not incidental binding-list order. Cycles, unsupported service versions,
unknown workflow fields, duplicate writers, missing external input mappings,
and unimplemented free-text edge predicates are rejected. The only supported
gate representation is explicit Boolean equality over a produced JSON field.
This control-plan format is a declared execution subset, **not** a full
ServiceFlowIR or Argo validator/interpreter. It must not silently reinterpret
unsupported original IR conditions or claim G0–G5 validity.

## Public inputs and scenarios

Five fixed public CSV sources are copied from the original allowlisted
workspaces: transactions, executive sales, and the three vendor shipment
files. Their provenance and hashes are retained. The controls construct new
public reference compositions using the same service-family operations for
every source; no gold IR or hidden expected answers determine the graph.

Each source has five predeclared scenarios:

| Scenario | Required behavior |
|---|---|
| Nominal | All three operations run; exported headers and every row/cell equal the input |
| Extra row | The added actual row reaches both the structured artifact and exported CSV |
| Changed value | A changed cell reaches the export even though row count is unchanged |
| Missing file | Sensor reports unavailable; validation/export are skipped without fabricated outputs |
| Missing required column | Validation rejects that specific defect; export never runs |

Expected rows/counts are calculated from the actual public input via an
independent `csv.reader` comparison, not constants or private benchmark
assertions. The service implementation parses into dictionaries; the checker
compares input/output row sequences and checks actual structured rows, counts,
metadata, execution states, and applicable explicit JSON-schema expressions
from public catalog contracts. This covers the declared round-trip behavior,
not arbitrary business semantics or every possible service-schema rule.

Three negative controls must be detected for every source:

1. Replace the exported data with a constant header-only CSV.
2. Change an exported value while preserving its header and row count.
3. Remove the workflow gate and actually execute the missing-file case;
   attempting validation instead of skipping it is incorrect behavior.

The first two mutate saved execution snapshots; the third runs a deliberately
modified control plan. They are diagnostic negative controls, not model
repairs or new method results. Their detection is evidence about these tests,
not proof of exhaustive semantic test coverage.

## Actual public prompt rendering

`prompt_context.py` adds the public manifest, fixture paths, and contents to
the actual returned M3 generation and M4 repair prompts. A common append
function is available for other methods in a future separately frozen study.
Tests inspect the resulting prompt text, not only a populated Python view.

The rendered context requires explicit external fixture links, real producer
bindings, and explicit logical time when needed. It fails on unavailable input
context or the declared 64 KiB context limit rather than silently truncating.
Fixture text is labeled as data, not instructions.

The original experiment does **not** automatically use these new functions.
No old prompt is rewritten, and no LLM client is created. The runner saves a
context preview built from nominal public inputs only: changed-input and
negative-control cases are not included in the generation view. A future
generation experiment needs an explicit v2 harness/configuration that selects
these adapters and maintains equal public input availability across applicable
methods. That paid experiment is not launched here.

## Run

No API token is needed:

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/run_v2_family_controls.py
```

This performs 25 source/scenario checks and 15 negative controls across five
public CSV sources. The transport runs in the existing network-disabled
sandbox. An expected invalid-input rejection is checked separately from a
sandbox/infrastructure failure; it is not counted as a successful normal run.

For a read-only preview:

```zsh
.venv/bin/python -u scripts/run_v2_family_controls.py --dry-run
```

Outputs are stored in a new `audit/outputs/package_v2_family__<time>__<id>/`
directory: `summary.md`, `run.json`, implementation/input fingerprints and
snapshots, public compositions and scenario fixtures, nominal-only generation
context previews, actual workflow traces and artifact bytes, semantic checks,
and preserved negative-control executions/snapshots.

The parent v2 replay must be complete and unchanged in the same environment.
The runner verifies its frozen input fingerprints before proceeding and then
checks the current implementation and input bytes at completion. Failed
controls remain visible. Resume an interrupted run using:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_family_controls.py \
  --resume /absolute/path/to/package_v2_family__YOUR_RUN
```

Recorded outcomes are skipped; interrupted sources use a new attempt folder.
Changing the implementation or input protocol requires a fresh condition.
The full source-level study has not been launched by the assistant; only
synthetic controls and read-only preflight are run during preparation.

Preparation verification: 112 focused tests passed across all prior audit
controls and candidate.2. The new tests include a full sandboxed synthetic
workflow, all five scenarios and three negative controls, actual M3/M4 prompt
text inspection, source-to-output value propagation, cycle rejection, and
failure on unsupported control constructs. Preflight verified the unchanged
parent input fingerprints and the 25/15 check roster.

## Decision after completion

Return the printed `summary.md` path. Only if all complete workflow controls
and negative controls behave as specified should we proceed to a small,
separately labeled v2 generation comparison or an explicit translation of
compatible saved compositions. Missing legacy input bindings must remain
missing unless a separate repair/alignment intervention is declared. Do not
launch all 110 pipelines or revise the paper's semantic-success rates from
these mechanism controls.
