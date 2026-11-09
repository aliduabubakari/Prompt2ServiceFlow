# Protocol 18: offline binding-derived IR assembly

The protocol-17 model patch eliminated writer conflicts but left six report
bindings pointing to undeclared artifacts and ten intent/binding list
disagreements. Its checked non-schema findings rose from 10 to 16. It supplied
no fixture links and declared no uncertainty. Keep this failed intervention;
do not call it a successful semantic repair.

Before another paid attempt, test an explicit representation policy. In this
new condition, existing model-authored port bindings are canonical. Project
the redundant intent input/output lists from them. For an artifact name already
chosen by the model on a required, artifact-channel, cardinality-one status
output, create the missing declaration only if it has exactly one bound writer
and no use as any input (including stale intent input lists). No new artifact id
or port binding is selected by the harness.

The public `assembly_policy.json` declares the status metadata: artifact kind,
status type/role, JSON media type, internal sensitivity, workflow persistence.
Display name is the existing artifact id, producer is its single bound writer,
and consumers are empty. These metadata choices are a labeled v2 policy, not
facts uniquely implied by the catalog. No report content, success value,
lookup table, business output, or fixture data is created.

Existing artifacts are immutable. Existing status artifacts with ambiguous
roles or meanings require review rather than automatic retyping. Never create
a missing business artifact or input. Abort without any assembly changes on
duplicate ids, inconsistent rosters, unavailable descriptors, unknown ports,
multiple output writers, missing input artifacts, or an undeclared output that
does not qualify for the unused status rule. No automatic graph repair occurs.

The complete source and derived documents must satisfy the original IR schema.
Preserve service/intent rosters, all port bindings and parameters, control flow,
policies, runtime, public identity, and every existing artifact value. Only
intent input/output lists and appended diagnostic declarations can differ.
The script fingerprints inputs and independently reproduces the prior saved
model patch, saves each assembly operation, and compares before/after static
findings and input context. It generates no semantic score and executes nothing.

This is not a lossless parser recovery: making bindings canonical changes the
authority assigned to redundant fields, and status metadata is explicitly
supplied by policy. Report it as a new deterministic post-processing condition.
Even zero remaining static findings do not establish actual inputs, meaningful
operation profiles, or runtime semantics. In particular, zero unresolved bound
input files with zero bound external inputs is not 100% input coverage; its
fraction stays null and its readiness is unknown. Do not insert fixture links
or fabricate the unresolved CRM reference source to improve a score.

## User-run command

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/run_v2_binding_assembly.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_binding_assembly.py
```

No API key is needed. The second command writes a new summary and derived IR
under `audit/outputs/package_v2_binding_assembly__.../`. Original outputs, prior
failure records, v1 scores, published deposit, and submitted paper stay unchanged.
Actual operation implementations and independent reference controls remain
necessary before any semantic execution or broader v2 experiment.
