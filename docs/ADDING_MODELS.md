# Adding a model or provider

The harness uses an OpenAI-compatible chat-completions interface. A new provider normally requires configuration, not a model-specific prompt change.

## 1. Create a model configuration

Copy `experiments/config/models.example.json` and edit:

- the local model alias;
- `model_name`, exactly as the endpoint reports it;
- `base_url`;
- `api_key_env`, containing the *name* of an environment variable;
- context and output-token limits;
- whether the model reports reasoning content;
- token prices, only when the provider publishes applicable prices.

Do not store the token itself. If price is unknown, omit it rather than entering zero.

## 2. Create a new freeze

Copy the nearest freeze as a candidate, assign a new unique `freeze_id`, set `status` to `candidate`, update model and endpoint metadata, and retain the declared method budgets. Never edit a published freeze in place.

## 3. Test compatibility

Run readiness with `--allow-unfrozen`, then one pipeline across M0--M5 with one worker:

```bash
python3 scripts/check_experiment_readiness.py \
  --config experiments/config/models.custom.json \
  --freeze-config experiments/config/freeze.custom.json \
  --models custom-model --scope corpus --allow-unfrozen --probe-completion

python3 -u scripts/run_frozen_experiment.py \
  --config experiments/config/models.custom.json \
  --freeze-config experiments/config/freeze.custom.json \
  --models custom-model --methods m0,m1,m2,m3,m4,m5 \
  --split main --instances hive_script --samples 1 \
  --max-workers 1 --skip-image-build --allow-unfrozen
```

Review parse status, gate profiles, usage accounting, M5 tool behavior, and any infrastructure classifications. Test five varied pipelines before promoting the freeze.

## 4. Freeze and scale

After the pilot criteria are met, set the design to `frozen`, commit the exact configuration and code revision, and run the corpus. Resume an interrupted batch with its `--batch-summary`; do not start a replacement batch simply because some method outputs failed evaluation.

Concurrency is provider-dependent. Begin at one worker, increase only after a no-error pilot, and keep the chosen value in the freeze. M5 may contend for local Docker resources even when the model endpoint supports high concurrency.

## Model-adapter compatibility

The provider-neutral adapter preserves assistant content, standard reasoning content, and tool calls. If a provider rejects the standard alternating message sequence, treat it first as an endpoint/template compatibility problem. Any adapter correction must remain provider-neutral and be tested against every supported reasoning and non-reasoning model; do not silently change the scientific prompt for one model.

