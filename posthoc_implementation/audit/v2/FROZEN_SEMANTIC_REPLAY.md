# Frozen v2 replay of saved compositions

This package freezes the verified real backend, numerical profile, conservative
completion rules, independent business checks, public task association, parser
dependencies, full original source roster and input hashes. It makes zero LLM
calls. Version 1, its scores, submitted paper, deposit and prior audits remain
unchanged. A freeze file is generated once during preparation; a code, rule,
input or task-association change requires a new freeze, not an override flag.

The denominator retains all 5,940 original cells: 110 pipelines, three models,
six methods and three repetitions. The 2,970 M0–M2 direct-Argo cells have no
execution route in this IR backend and are explicitly not applicable. The 2,970
M3–M5 cells retain missing, unreadable, unsupported and blocked observations.
Summaries pool strata and keep stratum labels in per-cell data.

## What execution requires

Only the previously reviewed public task/profile association is registered:
`extension/building_energy_window_aggregation` with `bounded-window-1`.
This association states where the public numerical contract was reviewed; the
runtime dispatch itself uses exact service/version/operation identities, not
pipeline or model names. A similar service roster in another task does not
establish equivalent numerical semantics. No private reference composition or
expected business output supplies a model choice or missing input.

Saved IR must choose the reference runtime, use the exact registered operation
labels, preserve its source identity, pass the public schema and applicable
structural/contract checks, and satisfy the real backend's input, artifact and
graph constraints. The raw and frozen-completion conditions are recorded
separately. Completion can project redundant intent lists, declare already-bound
unused required statuses and bind one unambiguous already-declared publisher
audit projection. All edits are logged. It cannot switch a mock runtime to a
reference runtime, interpret `default` or unknown operation labels, choose a
service or source, change parameters or generate business data.

Eligible conditions run six positive input variants and three expected invalid
inputs using network-disabled sandbox execution. Identical raw/completed IR
explicitly shares execution. Successful conditions must pass all nine checks.
No standalone process exit, output presence or status flag counts as business
success. The original G0–G5 and unchanged G6-Assert are not remeasured.

## Important current coverage limitation

Inspection during preparation found that the older available IR for the reviewed
task uses `runtime.execution_profile: mock` and unregistered labels such as
`default` or model-generated names. These are incompatible with the now explicit
contract. A batch with zero eligible cells is a valid coverage result and has
**no semantic-success estimate**. It cannot be described as improved semantic
accuracy, a zero-percent measured semantic score, or 110 pipelines evaluated.

The successful later v2 composition was generated with the new public execution
contract. Its six positive passes and three correct rejections are retained as
development evidence, excluded from the original-cell denominator. It cannot
be substituted for an older missing or incompatible model answer.

If the frozen replay finds no eligible outputs, the next work is to provide
reviewed real service implementations and public contracts for additional
families, and separately register generation under those contracts. Reusing
older graphs with reassigned operation semantics would be a different, clearly
labeled intervention, not a faithful replay or a way to recover old scores.

## Commands

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_frozen_semantic_replay.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_frozen_semantic_replay.py
```

No API token is needed. Execution is sequential. Missing/incompatible cells do
not stop the batch or disappear from reports. A crash can resume from its saved
output directory:

```sh
.venv/bin/python -u scripts/run_v2_frozen_semantic_replay.py --resume /absolute/path/to/output_directory
```

Completed case inventories and source hashes are verified before reuse. An
execution-started marker without a result is retained as unknown and is never
silently dispatched again. Results include `summary.md`, `cells.csv`, the frozen
plan, per-case checkpoints, raw execution artifacts when applicable, pooled
model/method aggregates, the freeze snapshot and input hashes. Evaluated-only
pass rates, coverage and declared-cell pass yield have distinct labels; zero
evaluated observations produce an unavailable pass rate, not a guessed score.
