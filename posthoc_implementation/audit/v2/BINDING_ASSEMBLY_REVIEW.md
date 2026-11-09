# Review of the completed binding-derived assembly

Evidence: `audit/outputs/package_v2_binding_assembly__20261025T185937Z__a26164af`.
Verified 50,921 input fingerprints, unchanged input status, and the completed
derived-IR/evidence inventory.

The explicit v2 policy added six declarations for existing unused status-output
bindings and projected ten redundant intent lists from the model's port bindings.
Checked non-schema catalog/dataflow findings fell from 16 to zero. Existing
business artifacts and port bindings were preserved. This supports the narrow
claim that these consistency defects can be resolved by declared IR assembly
rules without another model call. It does not establish semantic preservation,
correct business logic, or a corpus-level repair rate.

There are still no bound external input artifacts or explicit fixture links;
input coverage is unknown, with a null resolved fraction. The remaining 28
runtime-specification signals concern generic operation wording, unspecified
profile labels, opaque objects, and `any` payload shapes. These are not 28
proven semantic errors, but neither schema nor catalog acceptance supplies their
missing executable interpretation. No workflow or business assertion ran.

## Assertion and reference-source inspection

For the three preselected API/table-fusion cases, source inspection found six
held-out predicates per case. They inspect initial/final status records, success
flags, nonzero fixture-file/record counts, and upstream-artifact count. They do
not inspect the joined business output. The inspected native fusion scripts
describe files and emit status summaries; no join calculation appears in those
scripts. The public tasks also leave unresolved third-source roles: a territory
lookup, supplier master, or subscription-plan lookup is named without a clear
matching public fixture/derivation. The supplied support policy is not by itself
evidence of a subscription-plan lookup.

Do not turn these findings into invented fixture mappings, business formulas,
or success flags. They motivate evaluating assertion coverage independently of
model generation. This three-case observation must not be generalized to every
pipeline's runtime or oracle without a corpus inventory.

## Next offline protocol

Protocol 19 inventories assertion types, paths, and fields for all 110 original
cases, preserving strata. Its conservative telemetry-only flag describes scope,
not an automatic oracle-error or semantic-failure rate. Some tasks may properly
target telemetry. It also evaluates seven fixed synthetic witnesses per original
scenario for the three-case fusion family. Status-only or unrelated/empty-output
witnesses test business-output coverage; damaged status records test the
telemetry properties the predicates are intended to check.

The controls use the unchanged per-assertion evaluator. They do not execute any
workflow, test full gate admission, rescore a model, or construct a legitimate
reference answer. Synthetic status claims are not authenticated runtime results.
Weak business-output coverage alone does not explain low original pass rates;
output-path/payload compatibility and actual model/runtime failures remain
separate questions.

Protocol 19 passed 54 offline tests and preflight, verifying 51,064 inputs. It
will write private evaluator-only evidence outside public generation workspaces.
No API key is required; no live model or workflow call occurred in preparation.
See `ORACLE_COVERAGE_CONTROLS.md` for the user command and interpretation limits.

Keep these assertion details out of generation prompts and repair rules. Before
a prospective v2 semantic experiment, define public transformations, complete
input roles, implement them, and validate independent business-level assertions
and mutation controls. Preserve original failures and denominators. v1, the
submitted paper, published deposit, and original scores remain unchanged.
