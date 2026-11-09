# Public v2 API/table join and routing contract

Use the public task, candidates, catalog, schema and supplied source metadata.
Choose the ServiceFlowIR, service bindings, artifacts, source links, policies
and control flow yourself. Only the registered service/version/operation
labels are implemented. Select the reference runtime for real bounded local
calculation. No production APIs, secrets, streaming or conditional branches are
supported. Use complete JSON for generation/repair; the agent writes it to
submission/serviceflow.yaml. Follow the IR enum vocabulary.

This is a clarified development contract, not an assertion that the original
v1 task specified every rule below. The supplied manifest identifies the three
real public inputs. Its policy object is the reference source for this run.
The task's subscription-plan lookup is not provided and is not performed.
Freshness is not measured because no logical clock or acceptance rule is
specified. No absent source, policy, timestamp or expected output is invented.

## Inputs and operations

Three ingestion services independently read the supplied scenario-neutral JSON
manifest under fixtures/inputs/. Each ingestion binds one input-manifest JSON
artifact and emits its own JSON source bundle and distinct execution report.
The primary source is an array of flat scalar records, the secondary source a
CSV lookup table, and the reference source the actual JSON routing policy.
The supplied profile maps manifest keys and field roles; do not infer a source
from a private filename or create example data.

The source-contract validator binds all three distinct ingestion bundles to
its many-valued input_artifacts port. It checks source roles, shapes, identity
and join keys, unique primary record identities, unique lookup keys, finite
numeric lookup fields, and valid priority/tier policy labels. Missing join keys,
unknown priorities, duplicate lookup keys and unmatched customer identities
are rejected. Multiple primary records may share one valid lookup key.

The normalizer binds the validated bundle. It strips and case-folds the label
fields named in the profile, preserving record and join identities exactly.
Named numeric lookup fields become finite JSON numbers. Nested records and
unregistered numerical/output semantics are unsupported in this version.

The fusion service binds the normalized bundle. For each primary record, join
the unique secondary row on exact key equality. Preserve all primary fields;
prefix secondary fields with profile_, omitting the repeated join key. Reject
column collisions. Derive these additional fields from the actual policy:

- priority_weight = policy.priority_weights[normalized priority].
- tier_multiplier = policy.tier_multipliers[normalized account tier].
- routing_score = priority_weight × tier_multiplier.
- immediate_category = category is in categories_requiring_immediate.
- score_threshold_reached = routing_score >= escalation_threshold.
- churn_priority_trigger = churn label is high and priority_weight is at least
  the weight of policy.churn_high_priority_threshold.
- escalation_required = any of those three Boolean conditions is true.

The publisher binds the fused bundle and writes rows sorted lexicographically
by the mapped primary record ID, one CSV and an audit with actual source,
manifest, profile and CSV hashes plus record/escalation counts. The primary
bound artifact is the JSON publication bundle, not the CSV file. An optional
separate JSON report may project the actual publisher audit.

## Common compiler and validation rules

Use one primary JSON computation bundle and one status-typed execution report
per service. The validator takes three bundles; all other operations take one.
JSON computation types are any/json/object. Execution reports have data type
status and role status/report. A separate optional publisher audit has role
report and type json/object. Bindings, producers, consumers and intent lists
must agree. Declare data dependencies explicitly in control_flow; the compiler
does not add hidden edges. Independent source ingestion may form a parallel
group. Dependent stages cannot be labeled parallel.

The same conservative completion rules apply to M3, M4 and M5: project
redundant intent lists from existing bindings, declare already-bound unused
required status artifacts, and bind a uniquely declared unused publisher audit
projection. Raw IR and edits are retained. The compiler cannot choose missing
status IDs/port bindings, service choices, data sources, business parameters,
join keys or numerical results. No mock-to-reference or operation-label
translation is allowed. JSON/object bundles are compatible with any ports;
all other public port, cardinality, policy and schema checks remain enforced.

M3 generates once. M4 uses the existing bounded public-diagnostic repair loop.
Pi M5 uses its existing tool agent and the same four-call validator cap. Their
other registered budgets are unchanged. Public feedback contains nominal
execution/schema outcomes only. Independent business checks and evaluation
variants run after method termination and never enter prompts or repair tools.
