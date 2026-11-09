# Protocol 21: evaluator-only static output trace

The recorded-attribution audit retained all 2,970 original M3-M5 cells: 741 had
no saved IR, 1,432 failed public gates, 749 recorded assertion nonpasses, 37 had
scenario alignment failures, and 11 passed end to end. Of the assertion messages
within the 749 assertion-nonpass cells, 4,073 report missing/empty outputs, 83
report value/count mismatches, and 19 report evaluation errors. The larger
9,095 missing-output message count in the overall report also includes 5,022
messages from public-invalid cells; do not use those counts interchangeably.

This motivates inspecting actual retained writer code rather than another
model call. Select all 797 original public-valid cells, including the 11 passes.
Use saved IR, runtime manifests/scripts, corrected Main records and non-Main
score files, private assertion paths, and private artifact mappings. All
information remains evaluator-only. Never use a private canonical filename,
scenario, expected value, or artifact mapping as a model repair instruction.

## Static recognition and limits

Parse Python source as AST without importing or running it. Extract only a
literal JSON string passed to `json.loads` in the top-level `OUTPUTS` assignment.
Require the complete script AST to equal the current frozen deterministic mock
renderer with that output metadata. Also require its fixed invocation arguments
and known task fields. Unknown, missing, changed, or oversized scripts receive
no writer predictions. A strict subset of recognized files is not a complete
writer inventory; no-match conclusions remain unresolved for such a cell.

For recognized scripts, record their possible file paths and literal JSON,
CSV-copy/header, mock-byte, or fixed-text branches. These are retained-source
plans, not execution snapshots or proof of outputs during the original run.
In particular, the old template may write `.txt` for JSON/status declarations
without a non-null JSON exemplar. Identify this conditional behavior without
changing that behavior or renaming files. Literal JSON fields can be inventoried
for availability using the unchanged JSON-path helper; expected values are not
evaluated and no score is reconstructed.

Match the actual recorded assertion scenario/alias to its unchanged private
definition. Compare its requested path with recognized writers and, when exact
intent/port roles match, the model's existing artifact bindings. A reference-role
name difference is a diagnostic discrepancy, not permission to alias outputs
or proof that a renamed output has correct contents. Multiple writers and
incomplete code recognition stay explicit. Verify that the retained submission
path agrees with the original score before declaring recognition complete.

Retain runtime scenario names, assertion scenario names, and recorded unmatched
scenarios. Do not invent a scenario alias for multiple hidden cases. Do not
compile, materialize runtime, execute scripts, copy outputs, resolve a filename
from hidden answers, or recalculate semantic success. No new outputs are
substituted into any original score. Unknowns and inspection errors remain in
the 797-cell ledger.

## Run

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/audit_v2_output_trace.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_output_trace.py
```

No token is needed. Zero inference, workflow executions, and rescoring. A new
`audit/evaluator_only/package_v2_output_trace__.../` contains per-cell traces,
aggregate evidence, fingerprints, and summary. Original v1, submitted paper,
publication ledger, and all earlier audit records remain unchanged.
