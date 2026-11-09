# Proposed v2 artifact and input contract

This draft supplies general instructions for protocol 17. It is not a change
to the published v1 schema, catalog, gate scores, or reference data. Its purpose
is to keep schema conformance, binding correctness, and executable meaning
separate. No rule chooses a service, a parameter value, a fixture, or a business
result on the model's behalf.

1. **Bind required ports.** Bind every required service output, including a
   required execution report. Declare each resulting artifact and match its
   producer to the service intent. A report's declared channel/type must follow
   the public descriptor; a business output is not automatically an execution
   report. A model-authored gate expectation is not an observed gate result.
2. **Give outputs explicit identities.** Prefer a distinct artifact for each
   producing stage. Input and output lists must agree with the corresponding
   port bindings, and producer/consumer declarations must agree with actual
   bindings. Reusing one artifact name must not hide a transformation or imply
   an in-place update. Do not fix a writer conflict merely by listing every
   writer as a producer.
3. **Make merges explicit.** Multiple upstream outputs can be bound to a public
   `many` input port using distinct artifact identities. Multiple writers of
   the same artifact require a specified and supported merge/update operation.
   No such operation is registered for this pilot, so a multi-writer artifact
   remains an execution-review blocker even when a producer list matches the
   writers. This is a declared v2 runtime restriction, not a retrospective v1
   catalog violation. Read/write reuse alone is not proof of a graph cycle.
4. **Declare consumed public inputs.** Represent a fixture input as an artifact
   with no service producer, an explicit `fixture_ref`, and the appropriate input
   binding. Use only the supplied public fixture inventory and active scenario
   files. Declare consumers consistently. Do not fabricate a path, copy an
   expected result into an input, assume an implicit working-directory file,
   or use an unrelated source as a substitute for unavailable data.
5. **Keep unresolved inputs visible.** A public task may name a source without
   supplying its data, source-to-file mapping, or derivation rule. Report that
   uncertainty in the response's `unresolved_requirements`; do not invent a
   lookup table, relationship, or source value to obtain a pass. One file may
   serve multiple roles only when its content and the public specification
   justify those roles; the harness does not establish that justification.
6. **Do not infer runtime semantics from labels.** A generic operation-profile
   string, an opaque parameter dictionary, or an `any` port does not define a
   transformation. A real implementation and a public operation specification,
   verified through reference controls, are still required before execution.

These instructions are model-independent. This pilot asks the configured Qwen
model to choose a patch using the same public context and catalog as before.
The checker verifies declared structures and flags unavailable or unbound input
links; it does not infer semantic correctness from those checks. Model-declared
unresolved requirements supplement, but never replace, independent inspection.
