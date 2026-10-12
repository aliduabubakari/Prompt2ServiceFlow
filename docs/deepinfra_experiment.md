# DeepInfra experiment profile

DeepInfra v12 is the frozen model-independent five-model protocol for the primary
M0-M4 study. It keeps the completed v8/v9/v10/v11 evidence and the local-LM
archive immutable. V12 changes only orchestration: the full roster or one of the
five explicitly frozen singleton model blocks may be executed at a time. No
held-out Validation-20 result was inspected.

## Exact study size

The repository contains 110 complete benchmark instances: Main-40,
Validation-20 (held out), and Extension-50. It does not contain 120 instances.
The declared v12 study is therefore 8,250 cells:
`110 instances x 5 models x 5 methods x 3 seeds`.

A 120-instance study would require authoring and validating ten new,
non-duplicated benchmark instances before the experiment is frozen. Do not
execute the 110 instances as one giant batch. Use three resumable, immutable
split batches under one frozen revision:

1. Main-40: 3,000 cells.
2. Validation-20: 1,500 cells, run only after all tuning and protocol choices
   are frozen.
3. Extension-50: 3,750 cells, reported as a separate extension analysis.

## Five-model roster

The catalogue snapshot observed on 2026-09-09 is recorded in
`experiments/config/freeze.deepinfra.v12.json`:

| experiment id | DeepInfra API id | context | input/output USD per 1M tokens |
|---|---|---:|---:|
| `deepinfra-qwen3-8-2-4t-a95b` | `Qwen/Qwen3.8-2.4T-A95B` | 262,144 | 2.00 / 6.00 |
| `deepinfra-glm-5-2` | `zai-org/GLM-5.2` | 1,048,576 | 0.488 / 1.56 (35% promotional) |
| `deepinfra-kimi-k2-7-code` | `moonshotai/Kimi-K2.7-Code` | 262,144 | 0.68 / 3.40 |
| `deepinfra-deepseek-v4-pro` | `deepseek-ai/DeepSeek-V4-Pro` | 1,048,576 | 1.30 / 2.60 |
| `deepinfra-qwen3-coder-480b-turbo` | `Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo` | 262,144 | 0.30 / 1.00 |

Prices and availability are time-varying. The frozen configuration records
the rates used for cost estimates; report provider-billed cost separately if
rates change during execution.

## API key

Read the token without echo and export it only in the experiment terminal:

```bash
read -s "DEEPINFRA_TOKEN?DeepInfra API token: "
export DEEPINFRA_TOKEN
echo
```

The token is never stored in configs, prompts, responses, manifests, or batch
summaries.

## Candidate preparation

Build the Extension-50 public workspaces (Main and Validation already exist):

```bash
make experiment-build-corpus-workspaces
```

Run full-corpus readiness and five minimal provider probes:

```bash
make experiment-deepinfra-readiness
```

Do not repeat another all-model, one-pipeline pilot. Run one generalization
checkpoint using the cheapest roster model (Qwen3 Coder 480B Turbo), five
diverse Main pipelines, all five methods, one seed, and four workers: 25 cells.

```bash
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-deepinfra-pilot-five
```

Aggregate it and inspect gates, operational coverage, token components,
latency, LLM/validator calls, and costs:

```bash
make experiment-review-pilot BATCH_SUMMARY=/absolute/path/to/the/batch.json
```

The checkpoint completed with full operational coverage, no budget violations,
no stale errors, and plausible gate results. That checkpoint transfers to the
orchestration-only v12 protocol. Run Main-40 with the same cheapest model, all
methods, and all three seeds: 600 cells.

```bash
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-deepinfra-main-cheapest
```

Analyze that complete Main model block before funding additional models. The
method and evaluator remain identical for every model; model-specific prompt
or pipeline exceptions are prohibited.

## V12 repair and measurement policy

M4 still receives at most three repairs. Each repair starts from the candidate
with the best fixed public-gate rank: full pass, then longest consecutive
passed prefix from G0 through G6, then total passed gates, then fewer public
diagnostics. Later regressions remain in the audit log but cannot overwrite a
better submission. Repair prompts carry at most 60 unique public diagnostics,
mark violations no longer present in the best state as
`PRIOR—DO NOT REINTRODUCE`, and flag exact repeated diagnostic states.
Every completion after the initial M4 generation consumes this same budget,
including parse-seed repair. Thus M4 can never exceed four total LLM calls
when the repair budget is three. A recovered parse failure clears the stale
method error before evaluation.

Aggregation reports provider `finish_reason=length`/`max_tokens` as truncated
calls and runs. Wiring F1 is not applicable when both gold and submission have
no producer-consumer wiring pairs; the aggregate table reports the applicable
denominator separately as `wiring n`.

For planning only, applying the v8 `hive_script` mean (29,862 prompt and 6,251
completion tokens per cell) to the five v12 standard-tier prices projects about
USD 385 for 8,250 cells before cache effects. This is a weak one-instance
extrapolation; replace it with the five-pipeline estimate before funding
the full run.

## Repeats and concurrency

The full study uses temperature 0.2 with seeds 101, 202, and 303. The runner
records the selected seed in every run manifest. At temperature zero, three
runs would mainly measure provider nondeterminism rather than sampling
variation.

`--max-workers 4` runs independent M0-M4 cells concurrently inside one model
block. Models remain sequential, which makes rate-limit attribution, cost
tracking, and recovery clearer. Results are committed to the master summary
in deterministic declared-cell order after each bounded wave. If a provider
or rate-limit failure occurs, successful cells in that wave are retained, the
failed cell remains pending, and the printed resume command must use the same
`--max-workers 4` setting.

Start at four workers. Raising concurrency is a protocol change and should be
done only in a new candidate after a rate-limit pilot.

## Freeze and full execution

The v11 five-pipeline checkpoint completed successfully and is transferable
because v12 changes orchestration only. The frozen execution sequence is:

1. Run readiness without `--allow-unfrozen`.
2. Execute and review the cheapest-model Main-40 block.
3. Execute additional frozen Main model blocks.
4. Execute held-out Validation only after Main is complete, then Extension.

Each command uses the same frozen v12 protocol. The runner accepts the complete
roster or exactly one declared singleton model block; arbitrary subsets,
reordered rosters, and unknown models fail closed.

```bash
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-deepinfra-main-cheapest
# After reviewing the cheapest-model Main block, run all remaining model blocks:
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-deepinfra-main
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-deepinfra-validation
caffeinate -ims env PYTHONUNBUFFERED=1 make experiment-deepinfra-extension
```

Each full command uses three samples and four workers. Preserve every printed
batch-summary path; it is the recovery and aggregation anchor.

## Preserved evidence

The completed v8 pilot remains under `experiments/runs/`. The older LM Studio
batches were moved, not deleted, to the ignored local directory
`experiments/run_archive/lms-through-v7/`; its `archive_index.json` records the
original and archived paths and checksums.
