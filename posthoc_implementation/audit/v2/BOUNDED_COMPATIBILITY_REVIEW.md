# Review of the completed bounded-window compatibility audit

Reviewed 25 October 2026. Evidence:
`audit/outputs/package_v2_bounded_compatibility__20261024T224445Z__f82d616a/`.
Audit protocol 8.0.0 completed with no inspection errors, model calls, workflow
executions, or repairs. All 49,330 input fingerprint entries were reverified
when preparing this review. Previous evidence and published scores are unchanged.

## What the report establishes

All 54 original cells remain in the ledger. The 27 M0–M2 cells belong to the
separate direct-Argo route. Of the 27 M3–M5 cells, 21 saved IR files were
inspected and six were missing at their inventoried submission locations.

The category counts overlap: eight cells have checked catalog violations,
five have dataflow problems, one has duplicate structure identifiers, 19 have
v2 input-mapping gaps, and all 21 existing files exceed some narrow adapter
requirement. Twenty cells use registered services whose public descriptors
do not enumerate operation-profile values.

The following **mutually exclusive** partition is more useful for planning:

| Group | Cells | Interpretation |
|---|---:|---|
| No saved IR | 6 | Availability outcome; no computation tested |
| At least one checked catalog, structure, or dataflow violation | 12 | Fixing adapter dispatch alone will not resolve these checked issues |
| No above violation detected, but a v2 input-mapping gap exists | 8 | Current executor cannot consume the saved inputs without a mapping change or separate repair |
| Only adapter-limit and unspecified-profile findings | 1 | Candidate for a declared v2 compatibility interpretation, not a certified executable or semantic pass |

These groups sum to 27. They apply only to this pipeline's fixed cohort.
Absence of a detected issue is not proof that the full G0–G6 checks would pass.

The 43 catalog findings comprise 37 missing required service-port bindings
and six absent service/version references. The 23 dataflow findings include
five bound but undeclared artifacts, 14 writer/producer mismatches, one
declared producer without an output binding, and three multiple-writer cases.
These are finding occurrences, not numbers of independent failed workflows.

## The diagnostic candidate

`deepinfra-deepseek-v4-1-flash/m5/extension/building_energy_window_aggregation/2`
has the six registered services and an explicit active fixture-manifest link.
The static checks found no catalog, structure, dataflow, or v2 input-mapping
issue. Its six `operation_profile` strings are `bounded_batch`, and its
publisher binds two artifacts to the catalog's many-cardinality
`output_artifacts` port. Those two choices exceed the current adapter's exact
labels and one-data-output rule, without violating the checked declarations.

The saved publisher artifacts explicitly distinguish `role: output` with
`data_type: table` from `role: report` with `data_type: json`; the separate
`execution_report` is also bound. This is useful public information for
designing a general output-projection contract. It does not, on its own,
fully specify runtime payload schemas or what an arbitrary profile string
means. Do not choose behavior by model name, artifact identifier, or private
expected answers.

The source manifest records `agent_step_budget_exhausted`. Preserve this
original method status even if the saved artifact can later run under new
semantics. A new replay cannot retroactively turn it into a successful
original agent run.

## Root-cause interpretation

This audit establishes a mixture of saved-composition defects, missing
submissions, underspecified public execution semantics, and an overly narrow
new replay adapter. The missing input links are gaps under the explicit v2
mapping convention: the old catalog marks the generic input port optional,
so these are not automatically old contract violations.

Together with the earlier compiler controls, the findings explain why simply
replacing the runtime cannot recover all original outputs. They do not show
that the original G6-Assert oracle is numerically wrong, establish a corpus-wide
error attribution, or justify changing the submitted semantic scores. The
nine passing reference scenarios were evaluated under newly declared v2 rules.

## Recommended next experiment: two separately reported conditions

Prepare one fixed, versioned no-LLM study that retains all 27 cells, not a
sequence of retries selected by whether a model result passes:

1. **Compatibility interpretation without IR edits.** Declare the mapping
   from registered service identities to the external v2 execution profile,
   explicitly treating undocumented original profile labels as unresolved or
   overridden by that new condition, never as proven equivalents. Specify
   general many-cardinality output handling using explicit artifact roles,
   types, and public schemas. Preserve the submitted bytes and original method
   statuses. If a case cannot be interpreted unambiguously, retain it as
   unsupported. This is a new runtime interpretation, not faithful reexecution
   of already specified original service behavior.
2. **Conservative deterministic binding repair.** Start from the same cohort
   and runtime condition, then apply separately frozen, general rules for
   uniquely resolvable input links or required status outputs. Log each edit
   and its public evidence. Do not invent a missing submission, guess unknown
   services, resolve ambiguous writers by choosing a desired answer, or use
   hidden assertions as repair feedback. Keep ambiguous cases unresolved.

Both conditions must use the reference and negative-control gate before model
replay. Include all attempted/unsupported/missing cases in their accounting,
retain paired source identities, and report newly executed results separately
from original method outcomes. Some saved IR cells may remain ineligible in
both conditions. A successful candidate would establish a mechanism for this
case, not an overall semantic improvement across 110 pipelines.

No paid generation or broad corpus replay is justified by the present evidence
alone. Additional service families require their own public semantics and
verified controls before their saved outputs can receive new semantic scores.
