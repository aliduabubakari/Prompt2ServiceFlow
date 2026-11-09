# DeepSeek comparison under the unchanged relational v2.3 methods

This adds the second model already declared in the frozen v2.3 design. It
retains all nine completed Qwen cells and dispatches only nine new DeepSeek
cells. No Qwen failure is dropped or regenerated, including all three M5
non-passes. Methods, public information, compilation/completion rules,
business runtime, independent assertions, requested seeds and method budgets
are unchanged. There is no v2.4 method or model-specific prompt correction.

## Scope and interpretation

- Task: `extension/support_profile_context_join`.
- New model: `deepinfra-deepseek-v4-1-flash`, using the existing frozen model
  configuration in `semantic_methods.models.json`.
- New cells: M3, M4 and M5 for seeds 101, 202 and 303, sequentially.
- Retained: all nine Qwen cells from the completed seed continuation.
- Combined output: 18 cells, with one model/method summary and per-cell rows.

The context and reasoning declarations already differ between the two model
configurations; those declarations are preserved. No new availability,
context-support, provider determinism or price claim is made. Raw usage,
requests and responses are retained. Token counts are not billed-cost
estimates. Requested seeds do not guarantee deterministic provider behavior.

This is a model-robustness comparison on one development task after inspecting
Qwen results, not independent held-out validation or a corpus-wide semantic
score. Six positive variations and three expected rejections are checks within
each composition, not nine independent tasks. All valid non-passes stay in
the denominator, and invalid attempts stay in coverage. Do not keep changing
prompts, schemas or budgets until M5 passes. Any later budget sensitivity
requires a separately declared condition and must retain these results.

## Provenance and safeguards

The source Qwen continuation is
`audit/outputs/package_v2_fusion_v2_3_qwen_seeds__20261026T134856Z__e91d27c3`.
Its seed-101 cells reference the original pilot
`audit/outputs/package_v2_fusion_v2_3__20261026T124819Z__09cf6fa7`.
Both must be kept when moving/archiving these results. Raw files are retained
by verified references instead of duplicated; count every cell only once.

The new immutable continuation manifest pins its entry point, tests, this
document, original v2.3 freeze and Qwen source files. All original method and
Qwen-continuation hashes and checkpoints are verified before dispatch. The
old dynamic implementation inventory excludes only separately pinned
orchestration entry points; no method/public-tool/data file is excluded.
The original manifests, code and results are never overwritten.

The existing v2.28.3 Docker image identities must exactly match those used for
Qwen. No rebuild is necessary. Offline tests and fresh integration controls
run before inference. Failed controls dispatch no model call. Every new
attempt is checkpointed. Completed and interrupted paid attempts are not
automatically repeated. A process lock prevents simultaneous runs; repeating
the default command after a batch exists stops and gives a resume path.

## CLI

With `DEEPINFRA_TOKEN` exported and Docker running, from the audit workspace:

```sh
.venv/bin/python scripts/continue_v2_fusion_deepseek.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/continue_v2_fusion_deepseek.py
```

The dry run needs no API key or Docker daemon, makes no model call, and prints
nine retained Qwen cells and nine new DeepSeek cells. The live command prints
its output directory before dispatch. On interruption, resume that new output:

```sh
caffeinate -ims .venv/bin/python -u scripts/continue_v2_fusion_deepseek.py \
  --resume /absolute/path/to/the/deepseek/continuation/output-directory
```

Do not resume a Qwen output with this command or use the original runner's
`--full-design` as a substitute, because it would rerun completed Qwen cells.
The combined summary reports retained and new token totals separately.
