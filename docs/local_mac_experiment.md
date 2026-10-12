# Local Mac / LM Link experiment protocol

The frozen experiment uses the OpenAI-compatible LM Studio server exposed on
the experiment laptop at `http://localhost:1234/v1`. LM Link may execute the
model on the connected Mac while preserving this local endpoint.

## 1. Start and verify LM Link

```bash
lms link status
lms server start
curl -fsS http://localhost:1234/v1/models
```

The frozen identifier in `experiments/config/models.json` must appear in
the response. The A10 embedding identifier
`text-embedding-nomic-embed-text-v1.5` must also be available. Load one model
before its block when automatic loading is disabled:

```bash
lms load qwen/qwen3-coder-30b \
  --context-length 100000 --parallel 1 --ttl 86400 \
  --no-speculative-draft-mtp \
  --identifier qwen/qwen3-coder-30b --yes
```

This CLI build loads the recorded `qwen/qwen3-coder-30b@4bit` selected variant
through the base model key; verify `selectedVariant`, `contextLength`, `parallel`,
and `ttlMs` with `lms ps --json` after loading.

LM Studio does not require an API key for this configuration. The client uses
a non-secret placeholder required by the OpenAI SDK.

## 2. Primary pilot sequence (M0-M4)

M3 is Prompt2ServiceFlow without repair and M4 is the full fixed diagnostic-repair
system. M5 is not part of the primary comparison. The completed pilot batches
were tuning evidence used to promote v7 to `frozen`; they are not publication
observations.

First run one pipeline (5 cells):

```bash
make experiment-pilot-readiness EXPERIMENT_MODEL=local-qwen3-coder-30b

make experiment-pilot-one EXPERIMENT_MODEL=local-qwen3-coder-30b
```

Review the printed batch summary before continuing:

```bash
make experiment-review-pilot \
  BATCH_SUMMARY=experiments/runs/<one-pipeline-batch>.json
```

Then run the fixed five-pipeline pilot (25 cells) as a new batch:

```bash
make experiment-pilot-five EXPERIMENT_MODEL=local-qwen3-coder-30b
make experiment-review-pilot \
  BATCH_SUMMARY=experiments/runs/<five-pipeline-batch>.json
```

Do not resume either pilot from an older M5 or prompt-version batch. Resume only
an interrupted batch created with the same model, M0-M4 method list, instances,
prompt/compiler versions, and sample count.

Compiler-generated Python mocks run inside a network-disabled macOS Seatbelt sandbox.
On non-macOS hosts, pre-pull `P2SF_SANDBOX_IMAGE` (default
`python:3.12-slim`) so the validator can use the Docker sandbox.

## 3. Pilot promotion review

Before Main-40, inspect the immutable five-pipeline batch and record the decision.
The pilot is ready to freeze only when:

1. all 25 declared cells are present and scored;
2. there are no infrastructure, parser, or evaluation-pipeline defects;
3. gate statuses and first-failure classifications are populated and internally consistent;
4. every run has token accounting, and API-backed runs also have cost accounting;
5. M4 respects the repair budget and consumes diagnostics when its initial attempt fails;
6. generated submissions contain no private benchmark leakage; and
7. remaining failures are attributable to method/model behavior rather than the harness.

A pilot does not have to support the paper hypothesis. Do not tune merely because
M4 has a lower score than expected; change the implementation only for a documented
protocol, leakage, compiler, validator, or measurement defect.

## 4. Freeze before publication execution

The v7 publication condition is Qwen3 Coder 30B at 4-bit through LM Studio/LM
Link, with M0-M4. Do not mix providers or model variants in one primary batch.
The completed freeze records:

1. select the final provider/model and reduce the publication roster to that one condition;
2. record the exact model identifier, endpoint, context/output limits, decoding settings,
   quantization/provider revision where available, and cost basis;
3. record `primary_methods` as `m0,m1,m2,m3,m4`;
4. commit all experiment code, configuration, benchmark data, and schemas;
5. confirm a clean Git worktree;
6. run the complete test, lint, leakage, and readiness suites; and
7. recompute all frozen file digests after the last intentional change.

No prompt, compiler, validator, method, model, budget, or workspace change is allowed
after this point without creating a new freeze and invalidating subsequent publication
runs.

## 5. Publication execution order

Run Main-40 first with the frozen one-model roster and default M0-M4 methods:

```bash
python scripts/run_frozen_experiment.py --split main --samples 1
python scripts/aggregate_results.py \
  --batch-summary experiments/runs/<main-40-batch>.json --md
```

Only after the frozen Main-40 batch is complete should the locked Validation-20
batch be executed once:

```bash
python scripts/run_frozen_experiment.py --split validation --samples 1
python scripts/aggregate_results.py \
  --batch-summary experiments/runs/<validation-20-batch>.json --md
```

The runner writes `experiments/runs/validation_lock.json` after the completed
frozen validation batch and refuses silent reruns. This local-LM v7 protocol
covered Main and Validation only. Extension-50 workspace and runner support was
added later for the separate DeepInfra v9 candidate; see
`deepinfra_experiment.md` before claiming a 110-pipeline evaluation.

Run robustness samples and registered ablations as separate, pre-declared batches:

```bash
python scripts/run_ablation_experiment.py
```

## 6. Exploratory M5 (not primary)

M5 remains available for future appendix work through `scripts/run_m5_agent.py`
and `--methods m5 --allow-unfrozen`. Its Docker images and budget ablation are
not required by primary M0-M4 readiness. Use
`scripts/check_experiment_readiness.py --include-m5` only when conducting that
separate study.

## Operational guidance

- Execute models sequentially; do not mix model blocks under memory pressure.
- Load the selected model manually and omit `--auto-load-model` when LM Link
  model switching is unreliable. Run one `--models` value per batch and resume
  with the printed `--batch-summary` path.
- Load with the frozen 86,400-second TTL and record any unexpected reload.
- Prevent macOS sleep for long runs and record thermal/power settings.
- Use `--batch-summary` to resume; never aggregate by filesystem mtime for the
  paper.
- For v7, M3-M4 produce or repair only `submission/serviceflow.yaml`. The model
  serializes ServiceFlowIR as JSON (a YAML-compatible subset), avoiding
  ambiguous colon-containing scalars. The harness writes canonical YAML and
  `bin/compile` regenerates runtime and Argo files before validation. Public
  G6-Exec checks execution/schema conformance; private G6-Assert still measures
  semantic behavior and is never visible during repair.
- Local models have no API-token price. Report tokens, latency, wall-clock
  compute, energy if measured, and hardware amortization separately from API
  cost.
