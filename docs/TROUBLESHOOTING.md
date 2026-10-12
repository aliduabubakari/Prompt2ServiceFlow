# Troubleshooting

## `freeze status is candidate`

Candidate freezes require `--allow-unfrozen` for pilots. Full publication targets intentionally reject them. Complete the declared compatibility checks and create a committed frozen design before scaling.

## `models must exactly follow the frozen roster order`

A publication batch must use the exact model roster and order in its freeze. Use a one-model freeze for a one-model batch rather than selecting one model from a multi-model publication freeze.

## HTTP 429 or concurrency limit

Resume the same batch with `--batch-summary` after capacity returns. Lower `--max-workers`; endpoints such as a single self-hosted llama-swap deployment may allow only one active completion. Do not score the infrastructure failure as a model failure.

## Prompt-template role alternation error

Confirm that the endpoint’s chat template supports standard assistant/tool messages. Prefer a provider-neutral adapter correction or a fixed provider model template. Record the failed attempt and resume the same cell after the infrastructure/template issue is corrected.

## M5 says no model is loaded

For LM Studio, load the model manually and verify it with the OpenAI-compatible `/v1/models` and chat-completions endpoints before resuming. Avoid automatic model swapping when one model exhausts the host’s memory or LM Link does not reliably report the remote loaded state.

## Batch reports fewer unique cells than expected

Resume with the exact batch summary shown in the error. All immutable design arguments, including retrieval configuration, must match the original batch; omitting an argument on resume can be a mismatch if the batch recorded an explicit value.

## G6 execution cannot run

Do not execute generated code without the supported sandbox. Readiness reports the sandbox and Argo CLI state. You may separate generation from post-hoc sandboxed evaluation, but preserve the generated submission and link the later evaluation record to the original run identity.

