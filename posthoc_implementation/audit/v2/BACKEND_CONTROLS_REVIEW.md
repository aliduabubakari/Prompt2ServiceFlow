# Review of the completed reference backend controls

Evidence: `audit/outputs/package_v2_backend_controls__20261025T214224Z__b41245a7`.
Verified all 60,546 input fingerprints, unchanged source inputs, the completed
comparison evidence, and every newly produced mock execution snapshot checksum.

## Result and scope

Under the explicitly declared v2 window operation contract, all six frozen-mock
reference executions completed without a process error but failed the business
checks. The final bound JSON publication bundle was unavailable in all six.
The six verified real-profile snapshots passed the same backend-neutral checker.
All four constant/value/alert/missing-publication mutants were detected.

This demonstrates a substantive backend limitation in this control: successful
mock execution does not establish the window transformation. It is consistent
with the corpus trace showing all 5,410 retained public-valid scripts use the
mock renderer. It does not predict original-model accuracy under a real backend
or prove equivalence to undocumented v1 operation labels. The reference graph
is a control, never a substitute for a model prediction. The business oracle
derives expected values from public inputs and the declared v2 numerical rules.

## Integration now prepared

Protocol 23 adds `semantic_backend.py`, a runtime-package compiler/executor
entry point for the registered six-service window family. It requires exact
labels/versions, JSON bundle roles, explicit scenario-neutral inputs, consistent
intent/port/consumer declarations, supported profile rules, and supported control
flow. Unknown semantics do not fall back to mocks or receive automatic repair.
The profile contains no model id, pipeline switch, private expected answer, or
audit-run path. The existing controlled computation kernels are reused.

The public schema excludes original private reference provenance and evidence.
The new reference integration control therefore records a provenance-only
projection: four bookkeeping fields from the checksum-verified public manifest,
plus citations to actual unambiguous public task headers/objectives for each
existing source-step reference. It preserves dataset/version labels and all
business intent, binding, service, parameter, policy and runtime decisions.
If public step evidence is missing, compilation stops. This is reference-control
preparation only: no model prediction is repaired, and the old reference remains
untouched. All provenance edits remain in the new compile-plan evidence.

Preparation passed 42 offline tests and a strict preflight checking 60,628
inputs. No live integration workflow or LLM call was run during preparation.
The user CLI in `SEMANTIC_INTEGRATION.md` exports a fresh real package and runs
nine network-disabled reference scenarios: six business-positive cases and
three specific expected input rejections, followed by four business-output
mutation checks. Public output schemas and the real-backend receipt are checked.

Passing this gate will validate the entry point for one supported family, not
finish M0-M5 harness integration, an Argo deployment, corpus coverage, or a new
model semantic score. Future generation must select the real route explicitly
under a new frozen configuration and report unsupported operations/inputs as
coverage limitations. The old runtime and reported v1 outcomes remain immutable.

Original paper, dataset, model outputs, scores, published repository/deposit,
and earlier audit records are unchanged. No original low score is replaced by
the reference-control result.
