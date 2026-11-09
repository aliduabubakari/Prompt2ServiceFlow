# Original-corpus offline coverage planner

Package candidate: `2.0.0-candidate.2`; audit protocol: `6.0.0`.

## Purpose

Inspect all 110 original workflows and the saved results from all three
models, methods M0–M5, and three repetitions. The verified input roster
contains 5,940 model cells: 2,970 direct-Argo M0–M2 cells and 2,970
ServiceFlowIR M3–M5 cells, plus 110 reference-side implementation plans.

This is static analysis, not an execution experiment or a new semantic score.
There are no LLM calls, generated-code executions, container/image builds,
network requests, database mutations, or model-output repairs. The planner
only writes new diagnostic output files in its unique ignored output folder.

## What is examined?

For each original reference workflow and readable saved IR:

- Exact selected service/version pairs, missing workflow dispatch, and whether
  a standalone adapter exists without whole-workflow integration.
- Required public service ports/parameters and actual input/output bindings.
- Missing external fixture links, unsupported path forms, public file
  availability across active public scenarios, and upstream producer links.
- Control/data dependencies, cycles, multiple producers, original free-text
  edge conditions, gates, branches/merges, and fan-in/parallel-group review.
- Local artifact schema availability/syntax and unresolved schema references.
  Remote schemas are not fetched, and schema syntax is not full validation.
- Declared external-system types, bounded fixture resource labels, public
  network/credential policies, runtime image/GPU hints, logical-location and
  template requirements, and conservative deletion/cleanup review flags.

The public catalog's descriptor files are sanitized by the frozen workspace
builder. Their actual bytes are checked against `workspace.yaml`'s public
inventory, not confused with pre-sanitization descriptor pins retained in the
catalog index. Private catalog relationships are not loaded. Raw fixture rows,
credentials, and private assertion answers are not copied into coverage
reports. Original IR, schemas, and public fixture files remain unchanged.

Reference IR is used to describe required implementations, not to repair
model decisions or supply missing model bindings. Reference plans themselves
may contain incomplete or inferred requirements, and are not assumed to be
independent semantic truth. The information-sufficiency label is retained for
review. No private assertion file is parsed or evaluated to choose a cohort;
the inherited integrity manifest still hashes original benchmark files.

## Direct-Argo methods are a separate route

M0–M2 final `argo_generated/workflow.yaml` files are inspected for presence,
YAML resource structure, images, and script/container template counts. Inline
code, commands, SQL, and generated programs are never executed. They are not
converted into an inferred IR or assigned a comparable new end-to-end score.
This artifact inventory does not certify Argo validity or executable safety.

The prescribed final artifact locations are used. The planner does not search
intermediate repair attempts or raw responses for a better substitute. Missing,
invalid, oversized, and uninspectable artifacts remain in the cell ledger,
with the original method status retained separately.

## Cohort proposals do not use model scores

Reference-side candidates are ordered by:

1. Number of unique missing workflow service/version pairs.
2. Count of reported control-translation gaps.
3. Count of public input-interface gaps.
4. Network/credential review flags.
5. Deletion/cleanup review flags.
6. Stable pipeline identity for deterministic tie-breaking.

These are simple workload proxies, **not development-time estimates**. A
single cloud SQL service may require more work than several local services.
The deletion flag is a conservative text-based review hint, not proof that
every binding deletes data. Two policy flags may apply to the same service.

A separate conservative local shortlist excludes references with required
network/credential policies, deletion flags, or missing input-interface
requirements. If it is empty, the report says so instead of inventing a safe
local candidate. A tentative cohort begins with that shortlist when available
and adds up to two workflows sharing missing implementations, minimizing new
unique capabilities. It does not pad a cohort with unrelated workflows.

All original cells for a proposed cohort are listed afterward, including
missing/invalid outputs. Neither model availability, parse rates, previous
semantic/public-gate scores, nor observed corrected-runtime successes affect
ranking. Proposals require human review before a cohort is frozen or any new
execution support is implemented; they authorize no external action.

## Readiness is deliberately conservative

`service_roster_complete` means only that selected service/version names
occur in the current three-service workflow registry. It ignores other limits
and is merely a coverage upper bound. A standalone retention operation is not
counted as integrated workflow support.

The local mechanism-control plan is not a general original-IR translator.
Therefore this planner certifies **zero** original cells as execution-ready,
even if a service roster happens to be complete. Complete original reference
execution and applicable public/semantic checks remain required. An analyzed
IR is readable enough for inspection; it is not declared schema-valid or
semantically correct.

## Run

No API key is required:

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/plan_v2_corpus_replay.py
```

For a read-only roster count before writing a planning report:

```zsh
.venv/bin/python -u scripts/plan_v2_corpus_replay.py --dry-run
```

The default run scans every original case once and prints progress per case.
Large saved artifacts may take time to parse, but no API inference charges
are incurred. A declared 2 MiB per-artifact inspection limit is explicit;
oversized files are recorded as limited inspection, not missing or failed
model outputs. YAML aliases are traversed with identity/size bounds.

## Evidence and resume

Outputs are written under:

```text
audit/outputs/package_v2_coverage__<UTC time>__<id>/
```

Files include:

- `summary.md`: pooled original coverage and reference-side implementation shortlist.
- `pipeline_coverage.json`: all 110 reference-side service/interface/resource maps.
- `saved_cell_coverage.json`: all 5,940 declared model cells and inspection results.
- `service_backlog.json`: missing exact capabilities and their affected cases/cells.
  Public-catalog resolution states are retained. Unknown/invented service IDs
  require binding/catalog review, not automatically a new implementation.
- `cohort_proposals.json`: stable ranking, local shortlist, tentative shared
  implementation cohort, and its complete original model-cell roster.
- `aggregate_coverage.json`: machine-readable summary and proposal metadata.
- `run.json`, per-case `coverage.json`: checkpoints and detailed issue categories.
- `input_sha256.json`, `implementation/`, `verification.txt`: exact input/code
  evidence and synthetic verification results.

Parent family controls must be complete, unchanged, and in the same recorded
environment. The planner fingerprints the new implementation, original batch
manifests, and final artifacts, including previously missing paths. Original
files and code are verified again at completion.

Resume an interrupted planning run with:

```zsh
caffeinate -ims .venv/bin/python -u scripts/plan_v2_corpus_replay.py \
  --resume /absolute/path/to/package_v2_coverage__YOUR_RUN
```

Completed case records are retained, including reported failures. New attempt
directories preserve unfinished predecessors. Changing the implementation or
sources requires a new run. Planner/inspection errors are recorded and produce
`complete_with_errors`; investigate them before using recommendations. A
normal `complete` status means inspection finished with unchanged inputs, not
that the original workflows passed.

Return the printed `summary.md` path. The next decision is which complete
original workflow family to implement and verify before replaying saved model
outputs. V1, the published DOI, submitted results, paper, and all earlier
audit evidence remain unchanged.

Preparation verification: 130 focused tests passed, including a synthetic
checkpoint/resume test, score-independent ranking, retained missing/direct
artifacts, and verification of sanitized public descriptor bytes. Read-only
preflight confirmed all 110 pipelines and 5,940 original model cells. The
full source-level planner run has not been launched by the assistant.
