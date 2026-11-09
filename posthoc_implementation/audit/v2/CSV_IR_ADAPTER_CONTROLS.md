# Authored CSV IR adapter controls — protocol 32

This is the next prerequisite after the 108-cell static eligibility audit.
It does not replay saved observations, generate compositions or change paper
scores. All previous code, controls and evidence remain unchanged.

## What is implemented

The new adapter reads an explicit three-operation execution slice: filesystem
sensor, CSV validator and one PostgreSQL loader. Service versions, named and
typed ports, required columns, fixture links, producers, consumers, declared
dependencies and the availability gate must already be consistent. No binding,
column, conflict key, control edge or date is inferred. Unknown parameters and
unimplemented choices are refused rather than removed. Append and replace are
implemented; upsert, SFTP and typed CSV conversions remain outside this subset.

Filesystem resources are explicitly mounted from a finite named fixture list.
The sensor evaluates a nonrecursive basename glob against actual local files;
absolute logical paths never grant host filesystem access. Missing files skip
the gated validator and then its dependent loader. The loader is not inserted
into a source gate that only names the validator. Output locations use distinct
absolute and relative namespaces. The actual bound dataset has a hash receipt;
its requested output alias contains the same bytes.

Qualified table names preserve both schema and table. Each SQL identifier is
checked and quoted. An optional import columns list must be an exact identity
mapping of the actual ordered CSV header. A target label is retained as output
metadata and is never used as a connection address. The real database result
supplies rows_loaded and rows_imported, satisfying the declared public output
contracts. Actual port values are checked, without dropping properties to make
them conform. Output-schema failures can occur after side effects; this runner
always records before/after database state. Only the loader transaction is
atomic, not the entire workflow.

## Declared intervention and limits

This host-only adapter substitutes an isolated real database and a bounded
filesystem mount for explicitly named resource references. Each original
resource file and CSV byte stream is hashed separately from the intervention.
The source IR is preserved, and a separate hashed plan records execution
choices. No production connection or source script is run.

The intervention runs one business-operation attempt. Original schedule,
runtime and retry/policy fields are retained in the receipt as not executed.
This is not full Argo execution, an implementation of those policies, a public
M5 tool/container integration or certification of G0–G6. Full source IR schema
validation remains a separate prerequisite before any later saved-output replay.
The authored projections in this phase deliberately test the execution slice;
they are not submitted or scored as complete benchmark ServiceFlowIR documents.

## Authored controls and data

Controls are independently built from the public service interfaces and two
unchanged public CSVs. They do not read a saved model graph or a gold IR. Their
column requirements are explicitly declared from each control fixture header;
this is never applied as a repair rule to saved output. Both CSV sources use
the common public output contracts originally present in file_arrival_watcher.
The Validation source did not itself supply all those contracts: these are new
cross-dataset mechanism controls, not a claim of unchanged original task scoring.
These tasks have already been inspected and are development data here.

Per CSV source there are nine positive trials, two file-gate trials, eleven
refusal/rollback trials and six deliberately faulty results. Positive trials
include renamed intent/artifact IDs, renamed columns, absolute/relative output
locations, a different allowed schema, changed values, quoted Unicode/multiline
values and repeated append/replace. Refusals cover missing bindings/columns,
upsert without keys, nonidentity columns or unknown mapping, unresolved
templates, wrong port types/dependencies/gates/schemas, changed fixture bytes
and real transactional rollback. Six independent mutants cover empty output,
corrupt values, dropped rows, incorrect database schema/status and gate bypass.

The oracle reads the actual database and compares all header names, column
types, values and row multiplicities with an independent CSV parser. It does
not reconstruct expected database contents from loader output. There are no
LLM calls, original saved-output executions or new semantic-success percentages.

## Run

The prior 108-cell audit and its source pins/checkpoints are verified first.
The cached PostgreSQL 16 image must be available; this command does not pull
images. PostgreSQL runs in a disposable container without published ports or
host mounts. No model token or server is required.

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_csv_ir_adapter_controls.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_csv_ir_adapter_controls.py
```

The command saves a new output directory, input hashes, design, image digest,
verification log, authored projections, intervention manifests, plan hashes,
schemas, execution receipts, before/after database snapshots and SQL dumps.
An end-of-run output seal includes every evidence file except itself. Interrupted
control runs are preserved; rerun into a fresh directory. Any infrastructure
error or failed control prevents a successful completion status.

Only after reviewing both control gates should a separate frozen phase inspect
all 54 original IR cells and replay admitted cells with declared interventions.
Missing/ineligible cells stay in coverage. The 54 direct-Argo cells retain their
separate execution route. These two development tasks cannot establish a
semantic-success rate for the 110-pipeline corpus.
