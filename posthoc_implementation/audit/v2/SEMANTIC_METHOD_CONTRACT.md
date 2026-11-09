# Shared public execution contract for v2 M3, M4 and M5

Produce ServiceFlowIR using the public task, candidate sets, catalog and schemas.
Choose services, artifacts, parameters, input links, policies, source-step
accounting and control edges yourself. Use the supplied public metadata exactly.
Return a complete JSON object for generation and repair; the Pi agent writes
that object as submission/serviceflow.yaml using its tools.

The supplied numerical profile defines the behavior of the registered real
service implementations. Use the exact registered service/version/operation
labels. Other labels are unsupported. Select runtime.execution_profile as
reference: real local calculations over fixture files, without contacting
production services. Mock and production selections are not reinterpreted.
Only the declared bounded-batch family is implemented. Unknown parameters,
branching, streaming, credentials and unsupported service versions are rejected.

Bind the supplied scenario-neutral input-manifest role under fixtures/inputs/.
Each stage takes one JSON input bundle and emits one JSON computation bundle
plus one distinct execution-report artifact. Computation bundle data types are
any, json or object; roles are intermediate or output. Execution reports have
data type status and role status or report. An optional publisher audit is a
separate json/object artifact with role report. Its producer and output
intention must already be declared. The publisher computes its actual contents.
JSON/object bundles are compatible with public any ports in this v2 validator;
other port, schema, cardinality and policy checks still apply.

Keep producers, consumers, port bindings and redundant intent lists consistent.
Never use a status artifact as a business payload or share an artifact between
unrelated writers. Use exact public schema paths or omit an optional schema_ref
when none matches. Follow the IR enum vocabulary, including required/preferred/
not_required/unknown for idempotency requirements.

The same compiler-completion rules apply to all three methods. It may project
redundant intent lists from existing bindings, declare already-bound unused
required status artifacts, and bind one unambiguous already-declared publisher
audit report according to the supplied projection contract. Raw model responses,
raw IR and all compiler edits are retained. The canonical IR replaces the
submission source for subsequent validation and repair. The compiler does not
choose services, inputs, numerical parameters or business transformations.

M3 generates once without validator feedback. M4 uses its existing bounded
public-diagnostic repair controller. Pi M5 uses its existing file/tool agent and
matched validator budget. M4 and M5 receive only public gate diagnostics and
nominal execution/schema outcomes. Business assertions, expected results and
evaluation-only input variants are unavailable to all methods. Those checks
are applied only after the method has finished and its submission is fixed.
