# Review of the completed before/after contract audit

Evidence: `audit/outputs/package_v2_candidate_contracts__20261025T182902Z__ba7f7ecf`.
The run is complete, with source inputs unchanged. Verified 50,894 pinned inputs
and the completed before/after evidence inventory. The audit independently
reproduced the saved eight-operation enum patch.

| Observation | Before | After |
|---|---:|---:|
| IR schema violations | 8 | 0 |
| Checked non-schema catalog/dataflow findings | 10 | 10 |
| Explicit artifact fixture links | 0 | 0 |

All non-schema diagnostics and the inspected input/writer context stayed the
same. Six required execution reports are unbound; three service outputs disagree
with declared artifact producers; and one artifact has conflicting writers.
These are ten findings in one candidate, not ten independent failed pipelines.
Read/write artifact reuse is an additional review cue, not a reported cycle.
Other context and literal-type findings remain separate in the detailed files.

This provides a clear boundary for the root-cause analysis: resolving schema
vocabulary errors did not fix this composition's bindings or dataflow. It does
not establish that those issues explain the entire corpus's low semantic score.
No workflow or semantic assertion was executed.

## Proposed general correction

`PUBLIC_ARTIFACT_INPUT_CONTRACT.md` now states a labeled v2 draft: bind required
reports; give producing stages explicit output identities; keep intent, port,
producer, and consumer declarations consistent; require a specified implementation
for multi-writer merge/update behavior; bind consumed public fixture inputs
explicitly; and report unavailable source data without fabrication. Arbitrary
profile labels still need public operation semantics and actual implementations.
This draft does not rewrite the published schema or old scores.

Protocol 17 asks the same model for one restricted graph/input patch using
those general rules and the existing public task/catalog/schema/fixture context.
The allowed paths are derived from the existing intent/binding rosters; no
pipeline-specific replacement map or hidden expected answer is supplied. Service
choices/versions, parameter values, task, identity, policies, runtime, and all
unlisted fields stay fixed. The model must report unresolved requirements.
The harness supplies no artifacts, graph rewiring, or source assignments.

Offline preparation passed 57 tests and the parent-verifying dry run. The user
command is in `CONTRACT_REPAIR.md`: one API request maximum, requested patch
output budget 4,096 tokens, no automatic retries, no workflow execution, and no
semantic score. No live inference occurred while preparing this step.

Even if the next patch clears all checked static findings, inspect unresolved
input roles and the CRM reference-source specification independently, then verify
real public operation/runtime controls before execution. An empty uncertainty
list or zero static defects does not establish semantic readiness. Preserve
v1, the submitted paper, original scores, and all previous audit evidence.
