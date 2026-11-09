# Review of protocol 14: IR generation with reasoning disabled

Evidence: `audit/outputs/package_v2_reasoning_generation__20261025T154437Z__3e2dd560`.
The run is complete with unchanged source inputs. All 50,894 input fingerprints
and both saved request/response/result inventories verified. Neither condition
produced a usable ServiceFlowIR document. Run completion means the attempts were
recorded, not that generation succeeded.

| Condition | Stop | Completion tokens | Final-content characters | Strict JSON | Full IR schema |
|---|---|---:|---:|---|---|
| Full IR | length | 8,192 | 40,524 | invalid | not reached |
| Compact IR | stop | 2,630 | 12,124 | invalid | not reached |

Both requests asked for 16,384 output tokens and included `reasoning_effort:
none`. No separate reasoning field is recorded in either response. Unlike the
protocol-12 requests, both now contain visible text, but that text is not usable
IR. False identity/schema flags in the summary must not be interpreted as proof
of an incorrect identity: JSON parsing failed before those checks could finish.

## Full response

The content includes one literal `</think>` at character offset 22,396 (zero
based), with no opening `<think>`. Before it is a long JSON-looking block; after
it is another JSON-looking block that ends inside a service binding. Strict
parsing fails for the complete content and for each side separately. The prefix
fails at its end, while the suffix contains an unterminated string.

This is not a Markdown-fence removal problem. Do not supply missing delimiters,
promote the pre-marker block into a final answer, or replace the recorded failed
outcome. The marker shows an unresolved response-boundary issue; it does not
prove which backend component caused it. The repeated 8,192-token stops are
consistent with an effective serving limit, but the configured server cap has
not been independently verified.

## Compact response

The model stopped normally but emitted malformed nesting and unescaped quotes,
including quoted text that resembles nested JSON arrays. The first standard
JSON parser error is at character offset 698. This is not evidence of a codec
decode bug: strict JSON parsing fails before decoding. It also does not establish
that the positional format is reliable or easy for other models to produce.
Do not repair the syntax automatically and present it as a successful response.

## Next bounded check

Use the existing protocol-12 runner with
`--model deepinfra-qwen3-coder-480b-turbo`. This sends the same public CRM task
and full/compact output instructions under that model's existing declared
configuration. There are at most two sequential calls and no automatic retries,
runtime execution, repair, or semantic scoring. No SINTEF reasoning override is
silently applied to the cloud model. The runner verifies frozen parent inputs
and writes a new output directory. No original output or published result changes.

The comparison is diagnostic, not a causal separation of model and provider
effects: the model and serving system both change. If full IR works but compact
IR fails, retain the full representation and investigate the compact format
separately. If both fail, inspect the public context and output specification
before further scaling. If a candidate succeeds, inspect its contracts and
public input availability before semantic execution; the CRM family still has
the previously documented unresolved reference-source specification.

Existing census results already show that the original cloud Qwen M3/M4 runs
more often retained IR than the original SINTEF runs. That motivates this
diagnostic model choice but does not establish new semantic performance.

Keep default SINTEF, SINTEF reasoning-none, and cloud Qwen results separately
labeled. The transport failures are one contributor to low end-to-end success,
not an explanation for every G6-Assert failure. Runtime semantics, task/fixture
completeness, contracts, and the assertions remain independent audit questions.

## User-run command

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`, with
`DEEPINFRA_TOKEN` in the terminal environment:

```sh
caffeinate -ims .venv/bin/python -u scripts/run_v2_generation_pilot.py \
  --model deepinfra-qwen3-coder-480b-turbo
```

This is a new inference experiment, not a replay of saved model code. No live
inference was run during this review. v1 and the submitted paper remain unchanged.
