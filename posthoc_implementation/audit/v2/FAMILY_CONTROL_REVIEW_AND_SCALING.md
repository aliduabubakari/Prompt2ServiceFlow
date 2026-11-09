# Family-control review and zero-inference scaling decision

Review date: 2026-10-24.
Run: `../outputs/package_v2_family__20261024T202215Z__d01cbe02/`.

## Result

The run is complete: all five public CSV sources passed their five scenarios
(25/25 checks) and all three negative controls were detected for every source
(15/15). The verification log records 18 passing family-control tests.
There were no LLM calls. Recorded input fingerprints were reverified during
review and match the current input files. Original frozen source is unchanged.

This establishes the declared local availability/CSV validation/CSV export
mechanism: actual produced rows reach the next service, changed values and
rows are preserved, missing files gate downstream execution, invalid columns
stop export, and the tested incorrect outputs/removed gate are detected.

It does not establish semantic success on the original corpus. These are new
control compositions using five public fixture files from three original
pipelines, not executions of those original pipelines' complete tasks.

## Can we reuse saved outputs without more LLM inference?

Yes. The preferred next study is an offline, paired replay of saved model
outputs through a verified common executor. Re-executing and evaluating them
is still an experiment, but requires no generation API calls.

For M3–M5, the saved IR often contains the composition choices, while the
derived runtime scripts were produced by the old common mock compiler. That
compiler can emit schema examples, copy the first CSV, or write dummy text
rather than execute the selected service operation. Simply rerunning those
same scripts cannot supply the missing computation. Recompile the unchanged
IR under a verified versioned executor instead; retain old scripts as evidence.

For M0–M2, direct Argo/code is the submitted artifact. Do not replace it with a
new inferred IR and call that unchanged baseline replay. Its applicable
execution/evaluation path needs separate treatment, and no new comparable
score should be invented for an unsupported path.

New LLM inference is only needed if we want outputs generated under corrected
public prompts, or an explicitly model-based repair condition. It is not a
prerequisite for the next runtime/data/scorer investigation.

## Why not run all original workflows now?

An additional read-only check of the completed original inventory found:

| Saved model composition coverage | Count |
|---|---:|
| Model cells with inventoried nonempty binding lists | 2,211 |
| Those containing at least one candidate.2 supported service/version | 249 |
| Those whose entire service/version roster is supported by candidate.2 | 0 |

This is a service-roster check only. It already yields zero complete coverage,
even before testing fixture profiles, explicit mappings, graph translation,
or gate-language compatibility. It says nothing about whether the model's
abstract composition was otherwise correct.

Candidate.2 supports a specific local filesystem sensor, CSV validation, and
CSV export. The original workflows also require database operations,
enrichment, reporting, external APIs, and other services. Some saved outputs
also lack concrete input bindings. The prior replay retained 741 missing
final IRs and 18 invalid IRs; they cannot be silently turned into executions.

Thus an all-corpus launch with this executor would mainly measure missing
support, not corrected semantic correctness. More runs under unchanged
coverage will not close that gap.

## Separate the possible interventions

| Condition | What may change | Interpretation |
|---|---|---|
| Executor-only replay | Shared compiler/runtime implementation; saved composition choices stay fixed | Effect of correcting execution of existing outputs |
| Public-rule binding repair | Missing mappings or other bindings may change under declared public rules | Performance of a post-processed system, not the original model output |
| New generation/LLM repair | Prompts, generated choices, or model-produced revisions change | A separate v2 generation/repair study |

Never fill missing values from private assertions or gold bindings. A public
mapping that is absent or ambiguous must remain unresolved in executor-only
replay. Do not weaken tests or change requirements to make an old output pass.

## Recommended scaling sequence

1. **Inventory all saved original compositions once.** Produce a coverage map
   per original workflow: missing service implementations, public input links,
   supported control/gate constructs, schema constraints, and resource backend
   requirements. This is cheap, read-only, and requires no API calls.
2. **Choose complete original workflow families by implementation coverage.**
   Prioritize a small number requiring the fewest reusable missing capabilities,
   not the largest number of isolated service occurrences or the cases with
   favorable scores. Declare the cohort before examining revised outcomes.
3. **Implement and verify those whole original workflows.** Reference controls
   must exercise their actual task, not substitute the local round-trip task.
   Validate output data and side effects with negative and changed-input tests.
   Label fixture-backed resources explicitly; do not represent SQLite, dummy
   statuses, or fixture copying as validated real PostgreSQL/API execution.
4. **Replay the same saved model cells under both paths.** Use the old and
   corrected runtime with fixed IR, inputs, budgets/sample identities, and
   declared scenario mapping. Retain missing/invalid/unsupported observations
   and compare matched cells. Recheck applicable public gates for the changed
   runtime; do not combine stale public-validation results with new semantic
   checks and call that a newly validated full pass.
5. **Report distinct outcomes.** Keep original G6-Assert results separate from
   strengthened semantic checks. These assertions were inspected during audit;
   tests used to tune any repair must not later be described as unseen. Keep
   original v1 scores and archives unchanged and label the new evidence v2.
6. **Expand execution coverage only after complete-family verification.**
   Additional generation is optional later, not the default next expense.

No broad execution run or new generation was launched during this review.
The next implementation should be an original-workflow coverage planner and
then a declared end-to-end replay cohort, rather than another large batch of
the already-passing local mechanism controls.
