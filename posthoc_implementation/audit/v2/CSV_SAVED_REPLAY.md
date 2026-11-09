# Saved CSV IR replay — protocol 33

This new condition follows the completed protocol-32 authored adapter controls.
It freezes their input pins and all 953 sealed evidence files, including the
exact output fingerprint in the design. It does not edit the verified adapter,
old model outputs, methods, paper scores or releases.
The separate csv_saved_replay.freeze.v1.json lock pins this condition's runner,
admission/evaluation module, configuration, tests and documentation before use.
Changing any of those files requires a new separately labeled condition.

## Coverage and interpretation

All 54 original M3–M5 cells for file_arrival_watcher and
val_csv_to_warehouse_daily remain in the roster: three models, three methods,
two tasks and three samples. Missing, malformed and ineligible outputs retain
their identities, original statuses and reasons. The 54 direct-Argo M0–M2
cells are saved separately as a backlog; no generated scripts are executed.
These two previously inspected tasks are development data, not an untouched
validation set. This condition cannot establish a corpus-wide semantic score
or an equivalent end-to-end comparison between the original six methods.

## Admission is frozen before execution

Each available document must first pass its pinned full public ServiceFlowIR
schema. It must then meet the verified adapter's three-operation contract with
its original graph, versions, port types, fixture links and explicit parameters.
Output schemas must actually exist in that task's public workspace and remain
unchanged. The Main task's contracts are never borrowed for Validation.

Public fixture links use the previously declared scenario-neutral convention:
fixtures/inputs/X resolves to fixtures/scenarios/nominal/X, exactly. Other
explicit links must resolve inside the same public workspace. Missing links
are not filled from a unique available file or a reference graph. CSV bindings
must select that task's declared unchanged public source file. Required columns
must already be specified and present. An optional import columns list must
exactly match the ordered CSV header. Unsupported choices are blocked, not
removed or replaced with defaults to obtain a pass. No template dates, upsert
keys, control edges, table names or missing column declarations are inferred.

## Explicit runtime intervention

Only existing public filesystem-mock resources are rebound. A filesystem
resource must explicitly name its logical root in its original JSON. Its
bounded directory contains the original public CSV filename; the sensor's
path and glob parameters remain unchanged. Nominal resource/CSV bytes are
hashed and copied without editing. Multiple explicit CSV references can name
the same physical public file; the mount does not select among different data
sources or derive a filename from a model's glob.

A public PostgreSQL resource is rebound to the disposable control database.
Keep its explicit schema when present; otherwise this condition declares the
ordinary PostgreSQL default schema public. Preserve a schema-qualified model
target and provision that non-system schema inside the isolated database.
This is an environment interpretation recorded in the manifest, not a repair
of model parameters. Source resource bytes are retained separately. No source
connection URI, credentials, model-generated SQL or arbitrary program is used.

Execution uses the exact image digest verified by the controls. Every probe
gets a fresh isolated PostgreSQL container with no published ports or host
mounts. The adapter runs one business-operation attempt. Scheduling, original
retry/policy enforcement, full Argo execution and the public M5 agent/tool
route remain explicitly outside this intervention. Original runtime and policy
fields are retained as unexecuted in receipts, not removed from the source IR.

## Five probes per admitted cell

Three positive probes use the nominal CSV, a changed value and an added
duplicate row. The independent oracle reads the actual database and compares
all ordered column names/types and the multiset of every persisted value.
Duplicates matter. Reported rows_loaded and rows_written must agree with the
actual input count; success flags alone do not pass.

Two negative probes remove the CSV or a declared required column. They must
respect the saved gate or reject validation without database writes. A sensor
that merely observes an existing directory can therefore pass nominal loading
and fail the missing-file probe. Admission is not a promise of success.

Probe changes affect copied CSV bytes and their explicit intervention hashes
only. They never modify the IR's graph, bindings, columns, modes or schemas.
The missing-column probe selects the first saved required column, not a hidden
assertion or invented business rule. These probes test the declared TEXT,
row-preserving CSV-to-database subset; they do not certify unimplemented task
requirements such as SFTP, scheduling or richer business transformations.

## Evidence and failures

The complete admission roster and plans are saved before any model-output
execution. The run retains input hashes, full IR validation findings, actual
output schemas, original saved IR bytes, separate intervention plans, execution
receipts, copied fixtures, independent database before/after snapshots and SQL
dumps. Completed cell checkpoints hash every evidence file, not just the result
flag. The end-of-invocation output seal covers completed and incomplete attempts.

Infrastructure failures retain their attempt evidence and leave cells pending
for resume. A completed business-check failure is recorded and does not halt
the batch. Missing/blocked observations are kept in coverage without invented
semantic outcomes. The summary reports nominal and all-five-probe pass counts
beside the full 54-cell coverage and model/method admission counts. They are
bounded post-hoc results, not replacements for the published G6-Assert scores.

## CLI

No API token or model server is needed. Docker must be running, and the exact
cached PostgreSQL image from the prior controls must be present.

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/replay_v2_csv_saved_ir.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/replay_v2_csv_saved_ir.py
```

The dry run reads/validates all 54 documents but does not run their operations
or start a database. The actual command first runs synthetic verification tests,
then executes admitted saved outputs. There are no model-specific exceptions,
cell limit or success-based selection options.

On interruption or infrastructure failure, resume the printed output directory:

```sh
caffeinate -ims .venv/bin/python -u scripts/replay_v2_csv_saved_ir.py \
  --resume /absolute/path/to/package_v2_csv_saved_replay__RUN
```

Resume requires the identical input pins, design, plans, image and unchanged
checkpoint evidence. Completed cells are not rerun. An incomplete cell uses a
new attempt directory and fresh databases; older attempts remain available.
