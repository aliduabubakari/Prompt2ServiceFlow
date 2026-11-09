# V2 full/compact generation transport pilot

Package `2.0.0-candidate.5`, audit protocol `12.0.0`.
This is the first new-inference step after the saved-response audit. The
assistant prepares/tests it offline; the user launches the actual calls.
This local pilot depends on the existing frozen audit evidence/workspaces;
a portable v2 release will require separate packaging after validation.

## Purpose and bounded cost

The earlier failure cohort had 891 recorded length stops and no complete IR
candidate under conservative presentation extraction. This pilot tests a
general output-format change and better generation logging before another
large experiment. It does not promise a numerical semantic improvement.

Default: **two new inference requests**, one each for `full_ir_json` and
`compact_ir_json`, sequentially on one model/case/seed. No automatic SDK retries,
parse-repair calls, continuation calls, model loading, tool execution, Argo
compilation, workflow execution, or hidden assertion scoring occurs.

The default model is the existing SINTEF endpoint/model configuration, using
`SINTEF_LLM_TOKEN`. Cloud alternatives use `DEEPINFRA_TOKEN`. Identifiers are
inherited from the old configurations; no new availability, pricing, or server
capability claim is made. The configured output allowance is 16,384 per call;
you may lower it with `--max-output-tokens`. Increasing it beyond this pilot
budget requires an explicit new design/configuration. Actual charges, if any,
are provider-dependent; this runner records usage rather than inventing prices.

The default task is the first case in the preselected reference-only fusion
family, `extension/crm_sales_enrichment_fusion`. The other two eligible cases
are `extension/supplier_risk_api_table_fusion` and
`extension/support_profile_context_join`; select one using `--instance`.
This is exploratory development, not a held-out test. The known missing/unclear
third-source semantics are not silently fixed. Output/schema completion must
not be confused with solving those tasks.

## The two conditions

Both receive the same public task, candidate sets, catalog view, contract
schemas, fixture index/previews, verified identity values, model settings,
and configured output budget. Both are one-pass M3-like generation prototypes.
They are **not** a rerun of frozen M3, M4, M5, or an M0–M5 comparison. Fixture
previews are explicitly rendered in both conditions, correcting the omission
in the old initial IR prompt without changing only one arm's information.
Output schema/instruction lengths differ and are recorded; identical public
information does not mean identical prompt bytes/token counts.
Every model-visible file must match the frozen public workspace inventory;
newly added prompt/fixture/catalog files are rejected before inference.

- **Full IR:** author one complete ServiceFlowIR JSON object. Copy the
  supplied public identity values exactly. A different hash/identity is
  recorded as a mismatch, not automatically corrected.
- **Compact IR:** author a versioned JSON envelope with schema-derived
  positional records. Required object fields use the order declared in the
  public schema. Optional fields occupy an explicit final dictionary only
  where the generated schema declares it. Objects without fixed required
  columns, opaque parameter dictionaries, and conditional/union subtrees
  remain ordinary JSON. The compact output schema includes slot names/types,
  optional-field constraints, and local definitions.

The codec restores only four bookkeeping fields:

1. `ir_version`: the registered version constant.
2. `composition_id`: deterministic public split/case identity.
3. `catalog_snapshot`: verified public catalog identity/version/hash.
4. `source`: verified public task identity/hash plus the dataset labels already
   declared by the old public prompt, now explicit in this protocol config.

Every requirement, decomposition/evidence choice, service/version, parameter,
artifact/role/fixture reference, producer/consumer, control edge, policy, runtime
setting, and validation expectation is still authored by the model. No gold
IR/binding is read into the prompt or expansion. No missing required value is
filled from a schema default. Array slots cannot be omitted. Arbitrary parameter
keys/values are not renamed or guessed. Unknown fields, malformed JSON,
duplicate keys, and non-finite JSON numbers are rejected rather than repaired.

Encoding and decoding a valid full IR must preserve every semantic value
exactly. Round-trip tests cover opaque nested parameters, nullable producers,
optional fields, and conditional schedules. Generated compact/full equivalents
are saved for inspecting character-size differences on the **same** decisions.
Character counts are not claims about tokenizer savings; actual reported token
counts are retained separately.

## Logging and outcome handling

Before dispatch, save the exact SDK request arguments and a dispatch marker.
The configured endpoint must contain no embedded credentials/query token;
authentication comes from an environment variable only. No HTTP headers or API
key are written. Completion objects retain choices, assistant content,
available reasoning/tool fields, usage details, finish reasons, model identity,
and provider extension fields, with credential fields/token values redacted.
The saved SDK arguments are not a wire trace or proof of actual server limits.

Reasoning is never substituted for final content. Tools are never executed.
Known text-block content is handled explicitly; unsupported content shapes,
empty responses, filtering, unknown finish flags, syntax/schema failures,
identity mismatches, and inference errors remain separate outcomes. Missing
usage/reasoning metadata stay unknown rather than becoming zero.

A length stop is an operational outcome, not automatically a syntax-only
repair request. If its content nevertheless contains a complete IR, record
`complete_ir_with_length_stop` and its conformance separately; do not pretend
the response is necessarily incomplete or hide the stop. Valid schema/identity
also gets static contract/input diagnostics, but **no G6 score**. A model's
authored `validation_expectations` are merely expectations, never observations.
The legacy mock runtime is not compiled or executed.

Completed inference failures/length stops are retained on resume. An interrupted
call with a dispatch marker but no saved response gets
`interrupted_outcome_unknown`; it is not automatically charged again. A saved
completion can be reclassified offline without another call. Completed request,
completion, content, expanded-output, and result file hashes are checked on
resume. Unchanged parent/source/code inputs are checked before each new call
and at completion. The run never silently obtains a second answer for a cell
because the first result looks bad.

## Run

First, an optional offline preflight (no API key or inference required):

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

.venv/bin/python scripts/run_v2_generation_pilot.py --dry-run
```

Run the default **two-call SINTEF pilot** with your existing token environment:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_generation_pilot.py
```

If the environment is not set, enter it in zsh without putting the token into
shell history:

```zsh
read -s "SINTEF_LLM_TOKEN?SINTEF LLM token: "
export SINTEF_LLM_TOKEN
echo
```

Alternatively, choose **one** cloud model for its own two-call pilot:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_generation_pilot.py \
  --model deepinfra-qwen3-coder-480b-turbo
```

The other configured cloud ID is `deepinfra-deepseek-v4-1-flash`. Do not run
every example unless you intend to make separate new inference requests.
The runner executes its synthetic codec/transport tests before any request.
No live model is called by those tests.

Each run writes `audit/outputs/package_v2_generation_pilot__.../`, including
`summary.md`, immutable design/code/input fingerprints, both output schemas,
slot labels, configured requests, sanitized structured completion logs,
separate assistant text, expanded IR candidates, static diagnostics, reported
usage/latency, and round-trip/serialized-size observations where applicable.

Resume with the same model/case/output-budget flags as the original invocation:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_generation_pilot.py \
  --resume /absolute/path/to/package_v2_generation_pilot__YOUR_RUN
```

`complete` means the two outcomes were recorded, not that both generated usable
IR or that a workflow is semantically correct. Inference/ambiguous interruption
outcomes yield `complete_with_errors`. No v1 source/data/results/paper or
published repository/deposit is changed. Evaluate the findings before creating
a larger v2 generation or execution study.
