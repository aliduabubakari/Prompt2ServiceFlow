# A defensible v2 semantic-correctness study

This development plan preserves v1 and separates engineering improvement from
measurement. It commits to no numerical outcome and launches no new generation.

## The goal and the meaning of 50%

It is reasonable to build a useful general solution without solving every
failure. A 50% full-task success rate would be a measured result, not a default
chance baseline or the threshold for a valid paper. Success/failure being
binary does not make random workflow construction 50% likely to succeed.
Any chance baseline would need an explicit generation/selection procedure.

Choose the task scope, public inputs, service behavior, repair budget, held-out
checks, and denominator first. Freeze them and report the observed result,
whether above or below 50%. Do not weaken assertions, supply hidden answers,
remove difficult cases after observing failures, or keep changing rules until
a desired score appears.

## One general mechanism, with visible limits

Implement service-family rules through public catalog schemas and explicit
input/output roles. Avoid switches on model names, pipeline IDs, expected
counts, or known answers. Declare any new runtime interpretation and dataset
correction. Treat missing required inputs and undefined semantics as unresolved
until public evidence supports a correction; do not invent a successful task.

A family-limited study is legitimate if its scope is named and its tasks are
selected using predeclared public coverage/requirements rather than successes.
It must not be presented as a result for all 110 pipelines. Keep the already
selected three-source fusion family for specification review rather than
switching to a different family because its outputs look easier to pass.

## Evaluation and comparison

- Require reference computations and negative controls to pass before model
  evaluation. Check actual values and data dependence, not just exit status,
  artifact existence, status records, or schemas.
- Retain original valid held-out assertions where they match a well-specified
  public task. Investigate disagreements independently; a corrected oracle
  needs documented public requirements and reference/negative controls. Do not
  substitute easier checks just to increase semantic success.
- Keep original outputs, corrected-runtime replay, deterministic binding
  repair, and fresh generation as separately named conditions. Saved-output
  replay can test a new runtime/repair mechanism without more LLM calls; it
  does not measure new generation ability under corrected public instructions.
- For a new end-to-end M0–M5 comparison, give methods the same public tasks,
  fixtures/catalog access, appropriate matched budgets, and common applicable
  value checks. Direct Argo keeps its own execution route. Do not translate
  M0–M2 into reference IR to give it an unearned service implementation.
- Report all selected cells, original statuses, unavailable/unsupported cases,
  execution coverage, and correctness among actually executed cases. Also
  show a conservative end-to-end pass rate using all declared cells, where
  unexecuted cases are non-passes rather than asserted semantic failures.
  For example, two passing compositions from 27 declared cells must not be
  advertised simply as 100% correctness.
- Keep paired identities and repeated seeds. Uncertainty over tasks should
  account for repetitions belonging to the same pipeline rather than treating
  them as independent new tasks. Report token, latency, repair, and monetary
  costs for new generation/repair conditions.

## What can count as held out now

The current 110 pipelines and their aggregate outcomes have already been
inspected. A new split within them is a development/sensitivity check, not
automatically an untouched confirmatory test set. New input scenarios withheld
from repair development can test robustness of saved compositions, but do not
by themselves establish generalization to new task families. Claims about new
pipelines require genuinely new held-out cases whose results do not guide the
rules. Prepare/check public task semantics independently before revealing
those results. Freeze the implementation before running the final checks.

## Reproducibility and the submitted paper

Preserve the published v1 files, archived results, tag/commit, DOI, and reported
scores. Publish corrected code/data and new results as v2 with an explicit
change log, its own fixed source revision and deposit/version identifier,
and links back to v1. The GitHub default branch may advance while the v1 tag
remains reproducible; do not rewrite the v1 artifact to make old measurements
look as though they came from the corrected system.

If a revised manuscript reports v2 findings, identify which protocol/data/
runtime changed and distinguish new measurements from the submitted results.
Any material benchmark/evaluator correction should be described plainly.
Publishing or changing the manuscript is a later action, not part of this
local audit.

## Immediate action

First diagnose the 471 parse-error missing-IR cells using their saved text and
recorded usage/finish metadata. Empty or truncated content may require a later,
separately budgeted generation experiment; it cannot be reconstructed from
token counts. In parallel, resolve/document public input and contract gaps
for the preselected family before writing more execution kernels. Then freeze
the smallest useful general v2 mechanism and evaluate it under the rules above.
