# Public output-contract replay — protocol 37.0

This no-LLM experiment addresses two different defects exposed by protocol
36.1: generic text emitted for contract-defined JSON outputs, and malformed
outputs reported as evaluator exceptions. It preserves the original 2,970
M3–M5 identities and replays the same 797 originally public-valid runtimes.
The completed 36.1 run is the paired baseline, including its unsuccessful
observations. M0–M2 keep their existing direct-Argo scope.

## Compiler correction

Compilation receives only a saved model IR, its recognized original mock
runtime and a hash-verified public workspace. It resolves the exact bound
service, version and output port. Concrete inline JSON schemas in that
service's public descriptor and any declared local artifact schema must all
be satisfied. Existing valid mock examples are retained byte-for-value.
Otherwise the compiler derives a deterministic public-schema example using
the previous mock example policy plus conjunction handling. JSON null is
serialized correctly. Source service choices, parameters, wiring, declared
artifacts and task graph are not changed.

No pipeline/model switches or private expected values participate. Raw and
sanitized catalog digests are accepted only when explicitly recorded in the
public workspace manifest. Files outside inventoried catalog/contracts paths
and external schema references cannot be read by the compiler. Public schemas
with conflicting constraints or no supported example leave the original
output specification intact with an explicit unresolved reason. Missing
concrete schemas do not authorize inventing success fields, row counts or
other values. Unbound outputs are not assigned a guessed service or port.

The generated values are **public-contract mock examples**, as in the original
runtime. Their replay is a new compiler condition; it is not evidence that a
service performed the business transformation. Report this condition by name
alongside its original baseline, including any decline or unsupported case.

## Evaluator correction

Invalid JSON, unreadable text and missing JSON fields become explicit failed
output assertions. Their original evidence is retained. Missing outputs,
wrong values/counts and unresolved output roles cannot become passes through
this classification. Unexpected evaluator exceptions remain visible separately.
The frozen 36.1 reviewed scenarios, fixture bytes, predicate operators,
expected values and output-role association are reused. Literal and role-based
scores remain available. All comparisons are made on actual execution bytes.

The evaluator receives held-out metadata only after compilation is complete.
The generated-code sandbox has no network access and receives reviewed inputs,
not assertions or reference bindings. Every saved result includes its compiled
IR copy, scripts, public-schema sources, original/new output specifications,
executed tasks, snapshots and assertion outcomes. Full-batch and checkpoint
hashes cover those files. Original source files and version-1 results are
preserved.

## Controls

Before any corpus execution, the runner executes synthetic tests and an
authored sandbox control. The public contract requires a false boolean and a
minimum integer. The generated false value must pass the matching check and
fail a contradictory true expectation. Changing the held-out target cannot
change compilation. Additional tests cover conflicting public schemas,
private-path rejection, unresolved bindings, pinned catalog identities,
preservation of existing valid values, JSON null, execution-error handling
and unchanged IR/parameters/task graph. These controls are not model results.

## Run

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
caffeinate -ims .venv/bin/python -u scripts/run_v2_output_contract_replay.py
```

Planning and source verification can take several minutes. No API key,
model load, container image build or paid inference is needed. The command
first checks the frozen parent evidence and compiles plans from public inputs,
then runs the controls, followed by the eligible saved IR executions. A failed
control stops before those executions. `--dry-run` performs planning and hash
verification with zero runtime executions.

On interruption:

```sh
caffeinate -ims .venv/bin/python -u scripts/run_v2_output_contract_replay.py \
  --resume /absolute/path/to/package_v2_output_contracts__RUN
```

Checkpoints are immutable and completed cells are skipped on resume. A partial
batch is labeled interrupted/error. Summaries retain all original denominators
and both baseline and new assertion results. No higher score is assumed; the
run measures how much the shared public-contract compiler correction explains.
