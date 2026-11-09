# Protocol 19: evaluator-only predicate sensitivity controls

The assembly resolved the selected candidate's 16 checked consistency findings,
but it still has no explicit external input binding and its services retain
generic operation-profile semantics. That cannot establish execution or semantic
readiness. Further generic generation/repair is paused while auditing the
benchmark's assertion coverage for the three preselected fusion-family cases.
Also inventory assertion types, paths, and JSON fields across all 110 original
pipelines, retaining their strata. A conservative inventory flag identifies
cases whose predicates refer only to the four named telemetry fields or status
file existence. This is a scope inventory, not an automatic judgment of oracle
appropriateness: some tasks may legitimately target status reporting. Do not
equate that flag with a semantic failure or a false-negative rate.

Source inspection shows six held-out predicates in each case: initial success,
positive fixture-file count, positive fixture-record count, final success,
final status-file existence, and positive upstream-artifact count. Their paths
refer to status JSON files. The inspected native fusion scripts emit file counts,
hashes, and status summaries. These observations motivate a direct predicate
control; they are not evidence that every corpus oracle is similarly scoped.

## Isolation and controls

This audit reads the unchanged private assertion files only on the evaluator
side. It never adds their contents to model-visible public workspaces, prompts,
repair instructions, or service implementations. It never modifies actual run
outputs or assertion definitions. It writes synthetic control files to a new
directory under `audit/evaluator_only/`, explicitly outside generation inputs.

For each original assertion scenario, evaluate seven fixed witnesses with the
unchanged per-assertion evaluator:

1. Two synthetic status records and no business artifact.
2. The same statuses with an empty business payload.
3. The same statuses with an unrelated business payload.
4. Statuses with source record count zero.
5. Statuses with final success false.
6. Statuses with upstream count zero.
7. Statuses with the final status file absent.

The success flags and counts in these witnesses are explicitly synthetic claims.
They are not actual workflow results or proof of legitimate execution. Witness
values are fixed in code, not chosen from private expected values. The controls
test what the predicates accept, not whether a real service computed correct
data. A missing/empty/unrelated business artifact is not silently turned into
a valid reference answer. Detection of the status mutations provides a check
that the evaluator does reject the status properties it is meant to inspect.

Use the original per-predicate implementation directly; full publication-gate
aggregation, artifact remapping, model execution, and reference runtime execution
are outside this protocol. A synthetic predicate pass is never a full-gate pass,
new model score, corrected semantic score, or a template to repair real outputs.
Assertions with new types or escaping paths cause preflight rejection rather
than arbitrary evaluation. Preserve input and synthetic evidence fingerprints.

## Interpretation

If the status-only witness passes, the inspected predicates are insufficient
to establish the advertised business transformation. That is an oracle-coverage
finding, not proof that the low original pass rate was a false-negative error.
Weaker checks alone do not explain a low pass rate. The assertion coverage,
runtime output format/path alignment, public input completeness, and actual
business semantics remain separate causes to investigate.

Keep the three-case scope explicit. Before a prospective v2 semantic experiment,
define public transformations and complete input roles, implement them, then
validate with independently constructed business-level assertions and mutation
controls. Do not improve a score by adding success flags or copying held-out
expected results. Original v1 and the submitted paper remain unchanged.

## Command

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/audit_v2_oracle_coverage.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_oracle_coverage.py
```

No token is needed: zero API requests and zero workflow executions. The new
summary is written under `audit/evaluator_only/package_v2_oracle_coverage__.../`.
Return that summary for review before any further generation or semantic claim.
