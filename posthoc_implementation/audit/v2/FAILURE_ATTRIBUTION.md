# Protocol 20: classify recorded failures without rerunning or rescoring

The oracle controls showed that three fusion-family predicate sets accept
status-only synthetic witnesses while their business artifact is absent,
empty, or unrelated. The corpus inventory found 69 of 110 cases use only the
selected status predicates (35 Extension, 14 Main, 20 Validation). That scope
finding does not show that the original low scores are false negatives. It
also does not make the other 41 oracles complete semantic specifications.

Before another generation or repair, inspect the actual retained failures for
all 2,970 original primary M3–M5 cells: three models, 110 cases, three samples.
M0–M2 have no comparable G6-Assert route and remain outside this analysis.
Preserve case strata in the detailed ledger and report pooled model/method
groups. Do not mix in ablations or any new v2 pilot/derived candidate.

## Evidence sources

Require exact agreement between the 5,940-row original primary publication CSV
and the fixed saved-output inventory; select its 2,970 IR cells. Read source
manifests and retained score files without execution. The publication uses
corrected Main post-hoc scorer-1.2.1 records, so use those for Main instead of
the historical score files with empty/vacuous scenario results. Verify their
published semantic flags match the CSV. For Extension/Validation, use the frozen
manifest's recorded full-pass flag and the corresponding retained score file.
Retain missing score files, unscored outcomes, and read errors explicitly.

## What categories mean

Assign one recorded-stage category in this order: published pass; invalid
observation; no saved IR; recorded public-gate failure; assertion-stage execution
failure; scenario-alignment failure; unavailable/unscored assertion evidence;
empty/unverifiable assertion record; recorded assertion nonpass; or unexplained
nonpass. This is a chosen accounting order, not proof of the first causal defect.
Earlier stages can mask later defects, and an existing saved IR is not assumed
to be schema valid or executable. Keep original method status, failing gate,
evidence source, and all available assertion messages for every cell.

Independently count recorded assertion messages: pass, propagated execution
error, missing/empty output, evaluation error, value/count mismatch, unsupported
predicate, unexpected output, or other. Counts are per assertion, and their
cell-level categories overlap. Do not turn many missing files into many
independent failed pipelines. A missing-output message cannot identify whether
a compiler path, artifact mapping, unimplemented service, wrong model binding,
or other mechanism caused the absence. A value mismatch is not automatically
an LLM reasoning error. Unknown evidence remains in the full denominator.

The publication semantic-success flags are copied for reconciliation only.
No new success criterion, corrected score, workflow execution, or oracle run is
performed. Private assertion details remain evaluator-only and must not become
prompt instructions or a recipe for manufacturing compliant outputs.

## Run

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/audit_v2_failure_attribution.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_failure_attribution.py
```

No API key is required. The output is a new
`audit/evaluator_only/package_v2_failure_attribution__.../` with a 2,970-cell
evidence ledger, grouped counts, input fingerprints, and summary. It performs
zero model calls, zero workflow executions, and zero rescoring operations.
Original outputs, v1 results, the submitted paper, and published deposit remain
unchanged. Use the evidence to choose discriminating runtime/path controls or
public-specification work, rather than assuming the low rate has one cause.
