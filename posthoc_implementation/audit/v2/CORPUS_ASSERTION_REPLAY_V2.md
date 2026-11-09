# Zero-LLM corpus evaluator replay — protocol 36.1

Deadline scope: prepare corrected evidence for 30 October 2026 without new
LLM spending. Preserve the 110-task primary corpus and all 2,970 M3–M5 cells
(three models, three seeds). M0–M2 retain their original separate direct-Argo
applicability; this replay does not invent an equivalent business route.

## What this fixes

Every eligible saved runtime receives the complete reviewed scenario roster,
its original parameter maps and exact reviewed fixture bytes. Generated task
programs and task arguments are untouched. Actual outputs and execution/input
provenance are saved and sealed before reviewed predicates inspect them.
There are two paired scoring conditions over the very same snapshot:

1. Complete reviewed scenarios with the original literal predicate paths.
2. The same snapshots and predicate operations/expected values, associating
   output paths through unique exact service, version and output-port roles.

The second condition uses reviewed artifact mappings only inside the evaluator.
For repeated services it requires a unique matching intent or matching source
step references. The bound artifact must have one recognized physical writer
path. Ambiguous or missing matches remain unscored; they cannot pass an absence
check automatically. When no reviewed output role is defined, the literal
path is retained and explicitly marked as such. No existing-file search or
predicate outcome is used to choose a match. No files are renamed, fabricated
or copied between outputs. No reference composition replaces the submission.
The original score remains a third, separately labeled baseline; it was
obtained under different execution/input conditions.

All original-public-valid cells are considered, including original passes and
failures. Original-public-invalid and missing submissions remain in coverage.
Only programs recognized as exactly the already audited frozen compiler
template are executed. Unknown programs are retained as unsupported. The
original generated-code sandbox disables network access. Inputs contain no
gold assertions; those stay outside the sandbox. No model/API token is needed.

## Important meaning of the result

The retained v1 scripts are deterministic mocks. Correcting their evaluator
can establish reviewed-assertion coverage and outcomes, but cannot turn those
scripts into real business implementations. The report therefore labels both
conditions as reviewed-assertion passes and records business_semantics_verified=false.
The fact that a public task has task-specific predicates rather than status
checks alone does not make a mock execution a validated business operation.

This replay must not be used to manufacture an improved corpus semantic rate.
Keep its paired original/corrected assertion results separate from the real
PostgreSQL scenario pilot and the already completed real-execution v2 studies.
The latter can support bounded statements with their actual task scope and
sample counts. A full updated runtime/generation study remains review work.
The source programs may ignore reviewed parameters; such behavior is not
repaired by this evaluator. Failed checks and task errors remain visible.

## Controls and provenance

Before source replay, synthetic tests and an authored sandbox control verify
two different parameter-selected inputs, snapshot retention and rejection of
missing/duplicate scenarios and reused positive output. They do not count as
model results. Every cell stores the original and evaluated runtime metadata,
reviewed fixture hashes, executed/skipped tasks, actual output bytes, snapshot
hashes and both predicate outcomes. Literal predicate definitions are retained;
the separate role-associated copy changes only the selected path and records
the association. Missing or ambiguous matches cannot relax predicate values.
All evidence stays under audit/evaluator_only and out of generation prompts.

The complete original roster and admissions are frozen before execution.
All source code/data and the new implementation/config/tests/docs are hashed.
Completed cell checkpoints cover every retained evidence file. Interruptions
preserve earlier attempts; completed cells are skipped on resume. A task-level
execution error is recorded rather than converted into passing absent files.
Controller errors stop with a resumable partial report, not a completed batch.
The paired CSV retains every original cell, including pending, unsupported,
public-invalid and missing-source observations. These remain in full-roster
denominators. Conditional rates over the replayed subset must state coverage.

## Run

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/replay_v2_corpus_assertions_v2.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/replay_v2_corpus_assertions_v2.py
```

On interruption:

```sh
caffeinate -ims .venv/bin/python -u scripts/replay_v2_corpus_assertions_v2.py \
  --resume /absolute/path/to/package_v2_corpus_assertions__RUN
```

The local generated-code sandbox must be available. On this Mac that is
macOS Seatbelt; no inference service or PostgreSQL is used in this particular
diagnostic replay. The code does not pull images. No original result file,
paper source, v1 freeze or deposited archive is overwritten.

After completion, prepare paper tables from the full roster with explicit
coverage and paired conditions. Reviewed-assertion pass counts, independent
business validation and unsupported/unscored observations must remain distinct.
