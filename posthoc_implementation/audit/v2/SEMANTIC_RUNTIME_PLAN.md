# V2 plan after identifying the mock runtime backend

The evidence now calls for implementation work rather than more prompt tuning.
The original public-valid retained runtimes are structural mocks. Original
scores remain useful only under their original stated gate definitions; they
are not to be replaced by success flags, hidden-name aliases, or a hand-built
reference graph substituted for a model output.

## 1. Separate structural and business execution

Retain the old mock compiler as an explicitly structural backend. A prospective
semantic route must dispatch real, versioned operation implementations using
the model's actual bindings and declared public operation profile. Unsupported
operations, ambiguous input roles, or missing implementations must stop before
semantic execution and be reported as execution-coverage limitations. Never
fall back to schema examples, copied arbitrary CSVs, or constant output values.

The audit already has controlled implementations for a limited CSV workflow
family and a finite-window family. These are starting points, not coverage of
the original 110 full pipelines. Protocol 22 validates the window business
checker/backend contrast before integrating another generation experiment.

## 2. Complete public inputs and operation meanings

For each supported family, publish required input roles, file bindings,
parameter meanings, field types, duplicate/unmatched-input policies, output
relations, and scenario parameters. For unspecified original tasks, record
what is unresolved; any new semantics or added data must be versioned as v2
and cannot be called recovery of the original benchmark's hidden intent.

Provide the same applicable public context to all compared methods. Scenario
coverage must be explicit, including cases previously hidden behind an absent
public runtime/scenario convention. Do not silently generate extra hidden cases
or infer a missing lookup table from an expected answer.

## 3. Use logical output contracts without private-name repair

In v2, define public logical result roles and resolve a submission through its
declared intent/source-step and port bindings. Ambiguous resolution remains
unresolved; it is not guessed. An evaluator can then assess business results
without demanding an undisclosed physical filename. This needs a separately
declared evaluator contract, not retrospective copying to private gold paths.
Output type/suffix handling must match the actual serialized payload.

## 4. Assemble redundant IR fields under a declared policy

Keep model decisions and mechanical assembly distinct. The proven narrow
assembly policy projects redundant intent lists from existing bindings and
declares only unused status outputs already named by the model. It does not
choose services, inputs, business artifacts, parameters, graph edges, or data.
Report every policy-derived declaration and every unresolved choice. Do not
assume this policy is lossless or silently apply it to original scores.

## 5. Validate business behavior before model generation

Use reference compositions as controls only. Verify public-input-dependent
results, changed-input behavior, duplicate/boundary cases, invalid-input
rejection, and negative mutations with a separately implemented business oracle.
Status flags, file existence, and checksums supplement actual values rather
than replace them. Do not design the implementation to satisfy old private
assertion examples. Keep evaluator-only audit material out of model prompts.

## 6. Freeze a prospective v2 experiment

After backend/profile controls pass, integrate one real backend into a small
generation-and-evaluation route. Record model/provider configuration, all raw
responses, output limits, public context, repairs/assembly, runtime receipts,
coverage, and business results. Freeze rules before further measurement and
use the same applicable runtime/public information across methods. Existing
cases have already been inspected, so describe their results as development;
use new independent cases/input tests for the generalization claim appropriate
to what was actually held out.

Report both declared end-to-end denominators and conditional results within
supported/executed cases. Do not target a preferred percentage or treat 50%
as a random baseline. Do not pool new runtime/profile conditions silently into
v1 or claim all 110 tasks are semantically executable because one family passes.

No paper, published repository/release, original benchmark artifact, score,
or DOI is modified by this plan. Release v2 separately after verification.
