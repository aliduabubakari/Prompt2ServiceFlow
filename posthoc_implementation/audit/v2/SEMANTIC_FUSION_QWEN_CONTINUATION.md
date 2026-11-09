# Qwen repetitions under the unchanged relational v2.3 freeze

This continuation completes the Qwen portion of the already declared
three-seed development design. It does not introduce v2.4, change a method or
replace a previous observation. The original v2.3 freeze, scripts, prompts,
public catalog, completion rules, business runtime and assertions are kept.

## Cells and provenance

- One task: `extension/support_profile_context_join`.
- One model: `deepinfra-qwen3-coder-480b-turbo`.
- Methods: M3, M4 and M5, with the existing budgets and decoding settings.
- Seed 101: all three completed pilot results are retained by verified file
  references, including the valid M5 non-submission. They are not dispatched.
- Seeds 202 and 303: six new cells, run sequentially. Every outcome remains.

The source pilot is
`audit/outputs/package_v2_fusion_v2_3__20261026T124819Z__09cf6fa7`.
The continuation emits a single nine-cell summary and `results.json`, with
explicit lineage to the source files. Retained tokens and new-attempt tokens
are separately reported. Keep the source pilot directory when archiving or
moving the continuation; its raw files are referenced rather than duplicated.
Do not count the same seed-101 cells twice if pooling batches later.

The continuation is planned after observing seed 101. These are development
repetitions, not independent held-out validation. Six positive checks and
three expected rejections are checks within a composition, not nine tasks.
Model seeds are requested decoding settings, not a guarantee of deterministic
provider execution. M5 non-passes are not a reason to change its budget here.

## Immutability and safeguards

`continuation.semantic-fusion.v2_3.qwen.json` separately pins this entry point,
its tests and this document, the original method freeze, the source pilot and
the exact nine-cell roster. The old freeze dynamically inventories imported
repository modules: only this new continuation entry point is excluded from
that old inventory and pinned in the separate manifest instead. Every frozen
method/public-tool/data file is still checked. No old freeze is overwritten.

Before new inference, the command verifies original input and checkpoint
hashes, requires exactly the same Docker image identities as the pilot, runs
local verification and fresh integration controls. A failed control gate
dispatches no inference. This does not require rebuilding the existing images.

A process lock prevents simultaneous continuations. Repeating the default
command after a batch exists stops and requests an explicit resume. Completed
and interrupted attempts are never automatically regenerated. A partial paid
attempt is retained as an invalid observation; an uncheckpointed completed
result is adopted only after its cell identity matches.

## CLI

Keep `DEEPINFRA_TOKEN` exported in the terminal and the existing Docker images
available. From the audit workspace:

```sh
.venv/bin/python scripts/continue_v2_fusion_qwen_seeds.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/continue_v2_fusion_qwen_seeds.py
```

The dry run verifies inputs and prints three retained cells, six new cells and
the unchanged method freeze. It makes no model calls and needs no token or
Docker daemon. The paid command prints its output directory before dispatch.
On interruption, use that directory explicitly:

```sh
caffeinate -ims .venv/bin/python -u scripts/continue_v2_fusion_qwen_seeds.py \
  --resume /absolute/path/to/the/continuation/output-directory
```

Do not pass the original pilot directory to `--resume`, and do not use the
older runner's `--full-design` as a substitute: that would create additional
cells for both models and repeat the pilot in another batch.
