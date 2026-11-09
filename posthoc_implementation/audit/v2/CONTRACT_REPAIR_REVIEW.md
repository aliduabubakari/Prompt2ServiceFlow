# Review of the completed protocol-17 graph/input patch

Evidence: `audit/outputs/package_v2_contract_repair__20261025T184729Z__5eee8555`.
Verified 50,905 input fingerprints, unchanged source inputs, and the completed
request/response/patch/candidate/result/inspection inventories.

The model returned 12 allowed replace operations, using 1,478 completion tokens.
The candidate passes the IR schema and has no conflicting multiple writers or
input/output artifact reuse. However, the checked catalog/dataflow finding count
rose from 10 to 16. Do not report this as a successful contract or semantic repair.

The remaining findings are six `bound_artifact_undeclared` records and ten
`intent_binding_artifact_set_mismatch` records. The model bound six new execution
report ids but omitted their declarations. It also changed the port-binding
graph without updating the redundant intent lists. These are representation and
cross-reference consistency problems; their count is not a count of independent
semantic failures. The detailed file still retains 28 runtime-specification
signals, which are review cues rather than proof of incorrect business logic.

No explicit fixture links or bound external input artifacts exist. Therefore
the reported zero unresolved bound-input links has an empty denominator, not
evidence that all sources are supplied. The model's empty unresolved-requirement
list is not independent evidence of source sufficiency either. The CRM
reference-source specification remains unresolved.

## Next step: no further paid repair at this stage

Protocol 18 tests an explicit binding-derived assembly policy on this saved
candidate. The service port bindings become canonical for redundant intent
input/output lists. Missing diagnostic declarations can be added only for
existing model-chosen artifact ids bound to required, uniquely written,
cardinality-one, artifact-channel status outputs, with no use as inputs. The
metadata values come from a declared new public policy, not inferred defaults.
Only declarations are created; no report contents, success values, data rows,
fixture paths, business artifacts, graph edges, or port bindings are generated.

This is a new deterministic post-processing intervention, not lossless recovery
or a change to original scores. It cannot supply missing data or executable
operation semantics. Existing artifact metadata, including any ambiguous role
on an existing report, remains unchanged and requires separate review.

The planned operations are six diagnostic declarations and ten intent-list
projections. Preparation passed 64 offline tests and the dry run, verifying
50,921 inputs. No live inference or workflow execution occurred in preparation.
The user command is documented in `BINDING_ASSEMBLY.md`.

After this assembly, inspect the full remaining diagnostics and public input
readiness before execution. Zero static defects must not be reported as a
semantic pass. The next substantive prerequisites remain explicit source
provenance/mapping, public operation semantics, actual service implementations,
and reference/mutation controls. Preserve v1, all prior failures, original
scores, the published deposit, and the submitted paper.
