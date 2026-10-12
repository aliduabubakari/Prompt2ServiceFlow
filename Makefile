PYTHON ?= python3
CONFIG ?= experiments/config/models.deepinfra.v21.json
FREEZE ?= experiments/config/freeze.deepinfra.v21.json
MODEL ?= deepinfra-qwen3-coder-480b-turbo
METHODS ?= m0,m1,m2,m3,m4,m5
WORKERS ?= 1
RUNS_ROOT ?= experiments/runs/new-study

.PHONY: install test verify-results paper-analysis verify-analysis readiness pilot corpus

install:
	$(PYTHON) -m pip install -e '.[dev,analysis]'

test:
	$(PYTHON) -m pytest -q

verify-results:
	shasum -a 256 -c results/paper/SHA256SUMS

paper-analysis:
	$(PYTHON) scripts/prepare_evaluation_final_results.py \
		--primary-batches \
		results/paper/batch_summaries/primary-sintef-v19.json \
		results/paper/batch_summaries/primary-qwen480-v21.json \
		results/paper/batch_summaries/primary-deepseek41-v22.json \
		--ablation-batches \
		results/paper/batch_summaries/ablation-main-v24.json \
		results/paper/batch_summaries/ablation-extension-v24.json \
		results/paper/batch_summaries/ablation-validation-v24.json \
		--posthoc-main-g6 results/paper/analysis/posthoc_main_g6_assert.json \
		--out results/regenerated/evaluation_final

verify-analysis: paper-analysis
	$(PYTHON) scripts/verify_analysis_bundle.py

readiness:
	$(PYTHON) scripts/check_experiment_readiness.py --config $(CONFIG) \
		--freeze-config $(FREEZE) --models $(MODEL) \
		--scope corpus --allow-unfrozen --probe-completion

pilot:
	$(PYTHON) -u scripts/run_frozen_experiment.py --config $(CONFIG) \
		--freeze-config $(FREEZE) --models $(MODEL) --methods $(METHODS) \
		--split main --instances hive_script --samples 1 \
		--max-workers 1 --skip-image-build --allow-unfrozen

corpus:
	$(PYTHON) -u scripts/run_frozen_experiment.py --config $(CONFIG) \
		--freeze-config $(FREEZE) --models $(MODEL) --methods $(METHODS) \
		--split corpus --samples 3 --max-workers $(WORKERS) \
		--runs-root $(RUNS_ROOT) --skip-image-build
