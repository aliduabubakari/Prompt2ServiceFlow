# Complete reviewed-scenario execution pilot — protocol 35

This new v2 condition corrects the scenario handoff and evidence retention
identified by the completed 37-cell audit. It does not alter the v1 compiler,
scorer, paper results, saved IR, verified adapter or any previous freeze.

## Pilot and limits

Use the previously verified DeepSeek-Flash M5 file_arrival_watcher sample 0,
whose saved IR passed the five-probe CSV replay. This is an explicitly chosen
development control, not an untouched sample or a new corpus success estimate.
Execute both scenarios declared in the reviewed runtime metadata and evaluate
the six unchanged reviewed predicates plus independent PostgreSQL business
checks. No private artifact-name remapping or reference IR is used. The saved
IR's output identities must satisfy the existing predicates as written.

This runs the existing registered host kernels with the declared isolated real
database/resource intervention. It does not run the M5 agent/tool loop, generated
programs, full Argo, scheduling, retry or policy enforcement. It cannot replace
the original G6-Assert scores. Broader runtime coverage remains separate work.

## Common scenario handoff

The evaluator supplies explicit scenario IDs, parameter values and fixture
hashes. Every parameter must have a declared binding. Here fixture-file selects
the existing external CSV input slot; no missing IR binding or parameter is
invented. The source graph, service choices, business parameters, output IDs
and output schemas remain byte/structure checked against the admitted source.
Original resource JSON files are copied without editing.

The reviewed fixture root is treated as an input pool, not an exact filesystem
image. Only the selected CSV is supplied to the existing logical input slot
and bounded incoming-directory mount. An absent selection supplies no CSV;
unselected pool files are not mounted. This is an explicit new input/resource
interpretation. It is not proof that the original fixed CSV URI and full fixture
directory represented the reviewed scenario correctly. Both selected filenames
and original logical bindings are retained in the evidence. No predicate
expectations or expected outcomes are used to choose the supplied input.

## Execution and durable outputs

Every scenario starts a fresh isolated PostgreSQL container using the exact
previously tested image digest. Before any predicate is evaluated, retain:

- the scenario definition, exact parameter map and source/input/plan hashes;
- actual supplied CSV/resource bytes and a receipt for the handoff;
- actual registered-kernel task outcomes, artifacts and logical output aliases;
- independent database before/after snapshots and a SQL dump;
- the source/backend identity and a complete output snapshot manifest.

The snapshot contains the supplied inputs and invocation plan as well as
outputs. Verification checks its exact file roster and hashes, input selection,
mounted data, scenario ID, source IR, plan signature and parameter receipt.
Scoring reads those sealed bytes. Missing snapshots cannot pass a file-absence
predicate. Execution errors, duplicate/missing/unknown scenarios, empty checks,
wrong input identities and reused positive snapshots prevent a full-suite pass.

The reviewed predicates remain evaluator-only. Supported predicates are a
closed file_exists/file_absent/json_path_equals subset with bounded local paths.
They are evaluated only after a verified completed execution. In addition,
the independent business oracle checks all persisted CSV values, ordered TEXT
columns and duplicate multiplicities. For absent input, it checks real gating,
no loader invocation and unchanged database state. Status flags alone cannot
pass the combined condition.

## Authored control gate

Before replaying any saved IR, run independent authored controls for both
snapshot and tabular loaders. Each has three scenarios with arbitrary renamed
artifact IDs: two-row input, missing input and changed three-row input. All six
must pass, and all sixteen mutant checks must be detected:

- a missing scenario or duplicate scenario;
- a reused positive snapshot for a negative condition;
- a faulty handoff claiming negative parameters but retaining positive data;
- constant success/count flags with an actual observed empty database state;
- wrong business values despite passing status/count predicates;
- unsealed output modification or a missing snapshot manifest.

Snapshot mutations are labeled counterexamples, not genuine workflow/model
observations. Their source is the authored control evidence, never the saved
model replay. A failed control gate prevents saved-IR execution.

## Provenance and CLI

The condition verifies the completed alignment audit and saved replay seals,
original source hashes and fixture inventories. New implementation, controls,
configuration, tests and documentation are locked separately. Detailed inputs
and predicates stay under audit/evaluator_only and out of generation prompts.

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_reviewed_scenarios.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_reviewed_scenarios.py
```

Docker must be running with the previously tested cached PostgreSQL image.
No API token, model server or network download is needed. The dry run verifies
the design and inputs but performs no scenario execution. The actual command
first runs synthetic verification, then the authored control gate, then the
two saved-IR scenarios. The verification log distinguishes synthetic tests
from the declared saved-IR pilot. No LLM calls occur in any stage.

Each invocation creates a fresh output directory. Interrupted evidence stays
intact; rerun into a new directory. The final report distinguishes control
failure, infrastructure error and completed-suite failure. Both reviewed
predicate results and real business checks are retained; a completed report
is not automatically a semantic pass. Original publication results remain
unchanged regardless of the outcome.
