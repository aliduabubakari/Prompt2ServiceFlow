# SINTEF endpoint experiment profile

SINTEF v14 is a candidate single-model condition using the OpenAI-compatible
endpoint at `https://llm.sct.sintef.no/v1` and model
`qwen3.8:27b-nvfp4`. It does not overwrite or reinterpret DeepInfra v12.

The endpoint advertised a 65,536-token context window on 2026-10-01. A direct
chat probe accepted the frozen temperature, top-p, and seed parameters and
returned reasoning text plus aggregate prompt/completion usage. It did not
provide a separate reasoning-token count. The initial 64-token probe truncated;
a 512-token probe completed normally. Publication runs therefore retain the
established 16,384-token output cap and record truncation as before.

## Credential

Rotate the credential that was pasted into chat, then export the replacement
only in the experiment terminal:

```bash
read -s "SINTEF_LLM_TOKEN?SINTEF LLM token: "
export SINTEF_LLM_TOKEN
echo
```

The token must not be stored in the roster, freeze, shell history, manifests,
or batch summaries.

## Concurrency

The v13 one-pipeline pilot used four workers. The endpoint completed M0 and M1
but returned `429 concurrency_limit` for M2 and M3 after all retries; M4 never
started. V14 changes only the worker count to one. Do not resume the v13 batch,
because its frozen batch identity requires the original four-worker setting.

## Candidate sequence

Run readiness, followed by the one-pipeline and five-pipeline pilots:

```bash
make experiment-sintef-readiness
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-sintef-pilot-one
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-sintef-pilot-five
```

Review both pilots for provider failures, context errors, truncation, parse
errors, gate profiles, token usage, and latency. If they pass, freeze v14 before
running the publication batches:

```bash
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-sintef-main
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-sintef-validation
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-sintef-extension
```

Main, Validation, and Extension remain separate resumable summaries. The
single-model design contains 1,650 cells: 600 Main, 300 Validation, and 750
Extension.
