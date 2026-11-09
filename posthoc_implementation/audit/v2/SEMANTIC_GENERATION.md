# Protocol 24: one model answer evaluated through the real backend

Protocol 23 passed six positive business-output cases, three expected input
rejections, and four corruption controls on freshly exported real runtime
packages. This justifies a bounded generation pilot, not scaling to 110 tasks.
The supported family is the explicit window profile; other operations remain
unsupported until implemented and independently controlled.

## Fixed design and information boundary

Default: one Qwen-480B sample, seed 101, temperature 0.2, top-p 1, requested
maximum 16,384 output tokens, no SDK retry or model repair. Existing alternative
model configurations can be selected with `--model`; identifiers/capabilities
are inherited, not newly probed. Costs/usage and raw reasoning/tool fields are
retained; provider prices or effective server caps are not assumed.

Give the model the unchanged checksum-verified public task, candidate catalog,
artifact contracts, public schema, nominal fixture index/previews, verified
bookkeeping, new public numerical profile, supported operation labels and
input/output contract. The unique complete input-manifest role is declared from
public nominal files before generation. The deterministic assembly policy is
also public and recorded. This new information makes the task a constrained
explicit-profile composition exercise; it is not the original frozen M3/M4 or
a test of open-world service retrieval.

No reference IR, private assertion, cached output, mutated evaluation fixture,
or expected business value is inserted into the prompt. Historical inputs may
be hashed to verify parent integrity; that is not model visibility. The nominal
evaluation files must match the public nominal files exactly. No control-only
provenance projection or hidden-name aliasing is applied to model predictions.
Incorrect metadata, malformed JSON/schema, unsupported labels, or missing input
links remain failed/unsupported outcomes rather than being silently repaired.

The earlier control builder reserialized its nominal JSONL input. Before any
inference, verify that any byte difference is parse-identical with scalar types,
row order and duplicate rows preserved. If actual values differ, stop. For the
new pilot, stage a separate evaluation bank using the byte-exact public nominal
files and unchanged earlier evaluation variants. Record both source hashes and
all serialization differences. No original fixture or earlier result is edited;
the new backend and oracle compute provenance hashes from the actual staged data.

This local semantic condition requires `runtime.execution_profile: reference`.
Production and structural-mock selections are recorded as unsupported rather
than redirected. Argo deployment fields are preserved but not exercised here.

## Paired conditions of one answer

- `raw`: validate the sampled full IR, public static contracts and exact runtime
  scope; execute it unchanged if eligible.
- `assembled`: apply only the declared v2 redundant-list/unused-status-declaration
  policy to that same answer, retaining every operation. Services, parameters,
  existing artifacts, control edges, port bindings, source choices and business
  values stay fixed. This is not an LLM repair or an M4 result. If the IR is
  identical, explicitly reuse the raw execution; do not count another sample.

For eligible conditions, export the trusted real runtime and run six positive
business scenarios plus three expected input rejections in the network-disabled
sandbox. The independent checker computes actual expected metrics from public
inputs and checks actual CSV/publication values, public output schemas and backend
receipt. Do not substitute a status flag for numerical checks. Raw and assembled
results remain separate, including blocked and interrupted states. At most 18
scenario runs are possible; identical conditions execute only once.

The old literal `any`-type equality diagnostics remain separately visible. The
new declared JSON-bundle profile permits its registered JSON-compatible types;
this pilot does not claim a complete original G0-G5 or Argo gate pass. All
inspected tasks are development evidence, and these input perturbations are
robustness checks rather than an untouched task-generalization sample. There
is one generated observation and no statistical model-accuracy claim.

## Run

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`, with
`DEEPINFRA_TOKEN` exported for the default model:

```sh
.venv/bin/python scripts/run_v2_semantic_generation_pilot.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_semantic_generation_pilot.py
```

The first command is offline. The second makes at most one model request and
executes only eligible generated IR through the trusted backend. Model tools
or generated code are never executed. To resume use `--resume` with the exact
output directory and the same model flag. Completed answers are retained;
ambiguous inference or isolated-execution dispatches are never automatically
repeated. A completed report can still contain two blocked model outcomes.

Original benchmark data, v1 paper/repository/deposit, scores, model outputs,
and every earlier audit record remain unchanged. A positive profile result here
is a newly labeled development result, not a corrected original G6 score.
