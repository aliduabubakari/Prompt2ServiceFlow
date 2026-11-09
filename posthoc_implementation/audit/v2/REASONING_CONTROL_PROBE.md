# Small SINTEF thinking-control probe

Package `2.0.0-candidate.5`, diagnostic protocol `13.0.0`.
The previous full/compact pilot returned only `reasoning` text, empty final
content, and reported length stops at 8,192 tokens for both requests. The
saved SDK arguments requested 16,384, and the response fingerprint is
`fp_ollama`. This fingerprint is a clue, not proof of the installed server
version, exact software stack, or why the effective allowance differed.

## Documented control, locally unverified behavior

Current [Ollama OpenAI-compatibility documentation](https://docs.ollama.com/api/openai-compatibility#supported-request-fields)
lists `reasoning_effort` as a thinking control and describes `none` as requesting
no thinking for compatible models. [Thinking documentation](https://docs.ollama.com/capabilities/thinking)
explains that supported controls depend on the model and can be discovered
through the native `/api/show` interface. Unknown settings may resolve to model
defaults. The SINTEF proxy/version/model may differ, and a native route may not
be exposed. This probe tests observed behavior; it assumes no server support.

## Fixed comparison

Make at most **two tiny inference requests**, with the same model, prompt,
temperature 0, top-p, seed, and a **requested** 512-token output allowance:

1. `server_default`: leave reasoning control unspecified.
2. `reasoning_effort_none`: add only `reasoning_effort: none`.

Both ask for the same literal small JSON object. There is no benchmark task,
pipeline-specific instruction, repair, continuation, tool execution, or semantic
score. A server might ignore or override the requested token allowance: 512 is
not a proven spending/output cap. Actual token usage and any excess over that
request are explicitly recorded. Requests are serial and SDK retries are off.

Preserve assistant final content, available reasoning fields, usage/finish
metadata, request arguments, and response fingerprints. Reasoning is never
used as the submitted probe answer. Distinguish exact JSON, a normal completed
probe response, reasoning visibility, and the finish flag. HTTP acceptance
alone does not prove the option had an effect, and a short successful answer
does not establish a maximum server output budget or full-IR capability.

This is a new recorded model-serving condition. If later used for M0–M5,
apply and report the same setting across methods within that comparison.
Do not relabel the old default-reasoning experiment or change v1 artifacts.

## Run

With `SINTEF_LLM_TOKEN` set in your terminal as before:

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/probe_v2_reasoning_control.py
```

Optional `--dry-run` verifies old evidence and prints the plan without inference
or output creation. The assistant performs only dry-run and synthetic tests;
the actual two requests are left for the user. No server settings are modified.

Outputs: `audit/outputs/package_v2_reasoning_probe__.../summary.md`, request and
completion JSON, per-condition outcomes, input/code hashes, and synthetic-test
results. Parent fingerprints and completed response files are verified. API
credentials are read from the environment and redacted from logged material.

Resume only unchanged code/design/evidence:

```zsh
caffeinate -ims .venv/bin/python -u scripts/probe_v2_reasoning_control.py \
  --resume /absolute/path/to/package_v2_reasoning_probe__YOUR_RUN
```

Completed outcomes are not retried because they look bad. A dispatch without a
saved completion is recorded as outcome-unknown, not automatically charged
again. Review the results before another large IR-generation call. If the
control is unsupported or ineffective, seek the endpoint's serving settings
or use the already configured cloud-model comparison as a separate experiment;
do not repeatedly tweak prompt text or promote reasoning to a valid submission.
