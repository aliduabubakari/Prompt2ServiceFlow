# Protocol 14: IR generation with the observed reasoning control

The two protocol-13 requests both returned the exact requested JSON. The default
response recorded 239 reasoning characters and 60 completion tokens; the
`reasoning_effort: none` response recorded zero reasoning characters and nine
completion tokens. This supports testing the setting on the larger public IR
task. It does not establish the server's maximum output capacity or explain every
historical empty response.

This is a new serving configuration, identified as
`sintef-qwen3-8-27b-nvfp4__reasoning-none`. Never merge its results silently with
the original model configuration. If later used in a method comparison, apply
the same declared setting to every method in that comparison.

## Fixed comparison

Run the same CRM case and the same full-IR/compact-IR pair as protocol 12. Every
request field, including public prompt, model identifier, seed 101, temperature
0.2, top-p 1, and requested maximum of 16,384 output tokens, must match the saved
protocol-12 pair. The only added request field is `reasoning_effort: none`.
The server's effective output capacity is still unknown. Retain actual token
usage and stop reasons. Cache state, serving conditions, and one observation per
condition prevent a reliable latency comparison.

At most two sequential calls; no automatic retries or redispatch after an
ambiguous interruption. Raw responses, reasoning, final text, requests, schema
checks, and static diagnostics are retained. Reasoning is never promoted into
the final answer. Parent fingerprints and completed response files must verify
before starting. No benchmark runtime, semantic assertion, or repair is run.
Schema conformity is not semantic success. A completed run can contain two
unsuccessful generation outcomes.

## CLI

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/run_v2_reasoning_generation.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_reasoning_generation.py
```

Use `SINTEF_LLM_TOKEN` in the terminal environment. To resume, add
`--resume /absolute/path/to/the/new/output/directory`. Already dispatched calls
are not automatically repeated. v1, submitted paper, original scores, and earlier
audit designs remain unchanged. Review the new summary before any broader run.
