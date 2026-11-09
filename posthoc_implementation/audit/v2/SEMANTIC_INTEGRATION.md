# Protocol 23: real semantic runtime-package integration

Protocol 22 showed a backend limitation under the declared public window
operation contract: frozen-mock reference scripts executed successfully but
failed all six business-output controls, while verified real-profile outputs
passed all six and all four business mutants were detected. That is a mechanism
control, not a corrected original model score or all-corpus claim.

## Actual integration change

`semantic_backend.py` adds an explicit runtime-package compiler and executor
entry point. It supports the six registered window-family services at version
1.0.0 with exact public operation labels. The profile contains input-role and
field mappings plus the previously verified numerical rules; it contains no
pipeline or model id, private expected outputs, or audit-file paths.

The compiler validates the complete supplied IR schema and supported execution
subset before writing anything. It checks intent/port lists, artifact consumers,
declared producer graphs, explicit scenario-neutral JSON input links, versions,
operation labels, roles, supported control flow and parameters. It never repairs
a label, chooses a fixture, retypes an existing artifact, reconstructs a missing
input, or falls back to a structural mock. Unsupported semantics stop compilation.
The accepted `modality_policy.batch` is a descriptive tag only; `true_streaming`
is not supported. Extra parameter semantics remain unsupported.

The compiler exports a new trusted Python runtime package and explicit fixture
scenario manifest without overwriting an existing package. Runtime operations
reuse the independently controlled implementations. An execution receipt records
the backend, exact labels, IR/profile hashes, service versions and actual workflow
status. Public input profiles use relative aliases under `fixtures/inputs/`,
resolved against each active scenario's fixture directory. Scenario parameters
must be empty; parameter values belong explicitly in the public fixture manifest
for this supported profile.
Bound computation artifacts declare JSON/object/any bundles; the actual
published CSV is separate. Table-typed bundle reinterpretation from the older
compatibility study is not accepted here. The integration gate also validates
produced artifacts against applicable public schemas. This entry point does
not replace the experiment's other public catalog/policy gates.

This is a runtime-package integration, not a completed new M0-M5 runner, an Argo
deployment, or proof that every service family is implemented. A caller must
select this entry point explicitly; the old experiment and compiler are unchanged.

## User-run gate

Generate a fresh runtime package from the same reference control IR. Execute
nine local, network-disabled fixture scenarios: six positive numerical cases
and three cases that must reject conflicting duplicates, unknown registry groups,
or missing energy. Reuse the independent business-output checker for positives,
the established specific rejection oracle for negatives, and verify the new
backend receipt. Mutate the fresh nominal output in four ways and require the
business checker to detect them. No model-generated workflow or LLM is run.

Reference IR is a compiler control only, never substituted for model predictions.
Its original private provenance fields are incompatible with the stricter public
schema. For this reference control only, create a separately recorded view of
the four bookkeeping fields from the checksum-verified public task/catalog
manifest. This removes private provenance pointers and uses public `task.md`
identity. Preserve the original dataset/version labels and every business
decision. Replace private reference-evidence pointers with exact public task
step headers/objectives only when each existing source-step reference matches
one unambiguous public line. Save all bookkeeping and citation edits in the
compile plan; capabilities, source-step choices and all business fields remain
unchanged. Missing public evidence stops the control rather than being invented.
No model prediction
receives this projection, and the original reference file is not edited.
Business semantics are the separately declared v2 profile, not a reconstruction
of hidden original intent. Public/profile source integrity and all parent
evidence are verified; original v1, benchmark data, scores, paper and deposit
remain unchanged. Six correct outputs and three correct rejections must be
reported separately, not as nine successful executions or model accuracy.

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_semantic_integration.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_semantic_integration.py
```

No API token is needed. The second command writes a new
`audit/outputs/package_v2_semantic_integration__.../summary.md`. Keep inference
paused until this integration gate passes. Later generation needs its own
frozen public-context/runtime configuration and supported-task coverage ledger.
