# CSV to real PostgreSQL reference controls, v2 development package

This phase makes no LLM calls and executes no saved model workflow. It creates
new mechanism controls from public CSV bytes after the 110-task coverage audit.
The source tasks are Main/file_arrival_watcher and
Validation/val_csv_to_warehouse_daily. The latter is now inspected development
data and must not be described as untouched held-out validation in this study.
No original task result, paper score, fixture, method freeze or deposit changes.

## Public contract and scope

The source CSVs remain byte-for-byte unchanged in the new public fixture copy.
The old filesystem-mock PostgreSQL resource and absent warehouse binding are
not silently reused. A new public resource explicitly selects PostgreSQL 16
in an isolated disposable control container, database p2sf_controls, schema
p2sf_control and table records. The source task's transport/scheduler is not
implemented: this is bounded local-file detection, not SFTP, polling or cron.

All nominal CSV headers define this new control's explicit required columns.
Columns are ordered PostgreSQL TEXT NOT NULL, with ASCII SQL identifiers.
Strings, Unicode, quoted/multiline values, empty strings and duplicate rows are
preserved. There is no inference of numeric types, row filtering or business
meaning from fields such as status. These are declared v2 control decisions,
not recovery of an undocumented original schema or proof of full task intent.

Append preserves prior rows and adds every input row, including duplicates.
Replace atomically deletes prior rows and inserts the new rows in one database
transaction, keeping the existing compatible table/constraints. A mismatched
existing schema is rejected without mutation. Upsert, deduplication modes,
truncate/restore modes, arbitrary mappings/SQL and production resources are
unsupported and rejected. The public catalog interfaces are broader than this
explicit implementation subset; their complete behavior is not claimed.

The two distinct loader interfaces are retained:

- database_csv_snapshot_importer consumes CSV bytes and target_database, plus
  an explicit import_spec.target_table and load_mode. It emits a target reference
  and load_status. The control loads the original CSV only after validation.
- tabular_dataset_database_loader consumes ingested_data_object and
  target_database, plus explicit target_table/write_mode. Its new public
  metadata receipt identifies the exact validated dataset artifact, columns,
  row count and SHA-256. The loader follows that binding and verifies bytes;
  it does not guess a source URI, path, missing resource or table name.

The existing real local-file sensor and CSV validation kernels are reused
without modification. New modules implement the PostgreSQL subset. The three-
stage control is authored for mechanism verification; it is not a reconstructed
model IR or yet an integrated M3/M4/M5 runtime/compiler. Public G0-G6 scores
are not inferred from these database controls.

## Independent checks and evidence

The checker parses expected rows with csv.reader independently of the loader's
validation/DictReader path. It directly reads PostgreSQL catalog columns/types
and committed table values through separate connections. It checks every value
and row multiplicity, schema/order and reported write count. Status flags or
an in-memory dataset cannot substitute for persisted target state.

Each source has eight positive variants: nominal, extra row, changed value,
reordered rows, quoted/multiline Unicode values, allowed empty input, repeated
append and repeated replace. Missing-file gating must leave the database
untouched and never call the loader. Six expected refusal/boundary controls
cover missing columns, ragged rows, rejected empty input, unsupported write
mode, existing-schema mismatch and a real SQL CHECK-constraint failure. The
last verifies rollback of DELETE and INSERT in a replacement transaction.
The tabular loader also rejects a mismatched dataset hash.

Five mutants per source fake successful empty loading, corrupt a value, drop a
row, alter the schema or bypass a missing-file gate. All must be detected.
These variants are controls on two source datasets, not dozens of independently
sampled pipelines or semantic scores from an LLM.

Every trial saves its input/expected CSVs, before/after database snapshots,
failure reason/SQLSTATE, checks, outputs and an actual pg_dump SQL export.
The run records the resolved immutable Docker image ID/repository digest and
actual PostgreSQL server version. Original inputs and new code/policy are
hash-pinned before execution and rechecked afterwards. The container has no
published ports, uses network=none and ephemeral database storage, and is
removed on exit. No production database, host directory or credentials are used.

## CLI

The one-time PostgreSQL image download needs internet; subsequent controls
use the local image and isolated local engine. No API key or model server is
needed. From the semantic-audit workspace:

```sh
docker pull postgres:16
.venv/bin/python scripts/run_v2_csv_postgres_controls.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_csv_postgres_controls.py
```

The command runs synthetic contract/oracle and real PostgreSQL integration
tests before the public-source control batch. It prints its output directory
and final summary. A complete_controls_failed result is retained for inspection;
it is not relabeled as a model failure. A new invocation creates a separate
control attempt. There are no paid attempts to resume or regenerate.

For reproduction, --postgres-image may point to the locally available immutable
image ID recorded by a previous run; the server must still be PostgreSQL 16.
This phase has no saved-output replay eligibility or generation authorization.
After controls pass, strict port/resource/parameter/graph replay eligibility
needs a separate audit. A fresh generation study requires a new frozen public
contract and equivalent evaluation route for every compared method.
