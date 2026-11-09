# Review of the first v2 full/compact generation pilot

Reviewed 25 October 2026. Evidence:
`audit/outputs/package_v2_generation_pilot__20261025T133206Z__9ae4c439/`.
Protocol 12.0.0 completed with unchanged inputs. All 50,864 input fingerprint
entries and the request/completion/result files of both attempts were
reverified. No new inference or change to that completed experiment occurs
in this review.

## What happened

Both SINTEF requests returned `finish_reason: length`, 8,192 recorded completion
tokens, and **zero final-content characters**. The newly preserved `reasoning`
field is non-empty in both cases:

| Condition | Prompt tokens | Final content characters | Reasoning characters | Recorded completion tokens | Latency (s) |
|---|---:|---:|---:|---:|---:|
| Full IR JSON | 26,091 | 0 | 34,414 | 8,192 | 233.95 |
| Compact IR JSON | 26,853 | 0 | 34,789 | 8,192 | 175.53 |

The saved SDK request arguments specify `max_tokens: 16384` in both conditions,
with temperature 0.2, top-p 1.0, and seed 101. The responses report model
`qwen3.8:27b-nvfp4` and `system_fingerprint: fp_ollama`.

There was no submitted IR for the parser, codec, or contract checker to assess.
The summary's false schema/identity flags mean no conformant candidate was
observed; they do not show that the model supplied incorrect public hashes.
This is not a semantic assertion failure or proof that compact encoding
changes semantic correctness. Compact encoding did not improve completion in
these two requests, and no model-generated compact size comparison is possible
because no final compact document was received.

The second request reports 16,383 cached prompt tokens; the first reports none.
With one call per condition, this cache/order difference and other uncontrolled
serving factors prevent a general speed claim from the shorter second latency.
The calls consumed 52,944 recorded prompt tokens and 16,384 recorded completion
tokens in total (69,328 combined).

## Immediate diagnosis and uncertainty

The returned text is present only in `reasoning`, with no final assistant
content before the reported length stop. This now directly establishes that
response shape for these two requests. It is consistent with reasoning
consuming the allowance before final output, but it does not distinguish that
mechanism from a model-template/reasoning-parser or serving-budget issue.
The usage breakdown has no completion-token detail, so do not assign an exact
reasoning-token count from character lengths.

The current logs strengthen the earlier empty-response hypothesis; they do
not prove all 891 historical parse-failure calls had the same behavior. The
8,192 vs 16,384 discrepancy still needs serving/request compatibility review.
Logging SDK arguments is not a wire trace or a server configuration dump.

Do not loosen the parser, insert missing JSON, or treat the reasoning field
as the final submitted IR to obtain a higher score. The generation/serving
condition must first produce a usable final response. Do not scale this
unchanged SINTEF configuration to a new full experiment yet.

## Next small, documented control

Current [Ollama OpenAI-compatibility documentation](https://docs.ollama.com/api/openai-compatibility#supported-request-fields)
lists `reasoning_effort` and describes `none` as requesting no thinking for
compatible models. [Thinking documentation](https://docs.ollama.com/capabilities/thinking)
states that thinking controls/defaults depend on the model. The fingerprint
does not certify that this SINTEF deployment implements those current features.

A separate protocol-13 probe is therefore prepared: compare default behavior
and `reasoning_effort: none` on the same tiny literal-JSON prompt, with a
requested 512-token allowance per call. It makes at most two new requests,
records actual behavior, and does not change the model prompt by pipeline or
model-specific answers. Support/effect must be observed, not assumed from HTTP
acceptance. No endpoint settings are changed and no model is loaded/unloaded.

If a control works, register it as a new model configuration and apply it
consistently in a later full/compact pilot and eventual method comparison.
A tiny response passing does not guarantee success on the larger task or
resolve the missing third-source/public-runtime semantics. If the control
does not work, inspect the effective serving allowance/template with the
endpoint owner or use the existing two-call Qwen-Coder cloud comparison rather
than more unchanged SINTEF generations.

All original v1 measurements and the completed protocol-12 outcomes remain
intact. The v2 evaluation design still requires fixed scope, real value checks,
coverage accounting, and independent inputs before any semantic claim.
