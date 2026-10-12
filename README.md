# Prompt2ServiceFlow reproducibility package

This repository contains the benchmark, method implementations, frozen experiment designs, evaluation code, and paper-result records for **Prompt2ServiceFlow**. It is organized so that reviewers can inspect the reported observations, regenerate the paper tables, rerun the published experiment, or evaluate another OpenAI-compatible language model without changing the method logic.

## What is included

- The 110-instance corpus, with the original `main` (40), `validation` (20), and `extension` (50) labels.
- Implementations of M0--M5 and the G0--G6 evaluation pipeline.
- Frozen configurations for the three reported model runs and the Qwen ablation.
- All 5,940 primary observations: 110 instances × 3 models × 6 methods × 3 repetitions.
- All 1,650 confirmatory ablation observations: 110 instances × 5 conditions × 3 repetitions.
- Per-cell manifests and scores, immutable batch summaries, analysis tables, and checksums.

The published batches are complete and contain no invalid recorded observations. Twenty-four temporary ablation infrastructure attempts are retained in their batch audit trail; each affected cell was successfully rerun before analysis.

## Repository map

| Path | Purpose |
|---|---|
| `src/prompt2serviceflow/experiments/` | M0--M5, prompts, model adapter, compiler, validators, scoring, and harness |
| `benchmark/instances/` | 110 benchmark instances and hidden evaluation material |
| `experiments/config/` | Immutable publication model and freeze configurations |
| `experiments/m5/` | M5 agent/proxy source and frozen v2.1.8 container contexts |
| `scripts/` | Readiness, execution, scoring, analysis, and export entry points |
| `results/paper/analysis/` | Paper-ready tables and statistical summaries |
| `results/paper/batch_summaries/` | Six immutable publication batch summaries |
| `results/paper/runs/` | Per-cell manifests and scores used to regenerate the paper tables |
| `docs/` | Reproduction and extension guides |
| `tests/` | Unit, integration, schema, compiler, and golden tests |

## Quick start

Requirements: Python 3.11 or newer. Docker is additionally required for M5; the Argo CLI is required for direct-Argo G5 checks.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,analysis]'
pytest -q
```

Verify the packaged result files:

```bash
shasum -a 256 -c results/paper/SHA256SUMS
```

Regenerate the paper tables from the packaged run records:

```bash
make paper-analysis
```

See [Quick start](docs/QUICKSTART.md), [experiment protocol](docs/EXPERIMENT_PROTOCOL.md), and [paper-results reproduction](docs/REPRODUCING_PAPER_RESULTS.md) for the complete workflow.

## Running another model

Copy `experiments/config/models.example.json`, set the model identifier, endpoint, and name of the environment variable that holds the API token, and create a new freeze file rather than editing a published freeze. Never put a token in JSON or on the command line.

```bash
export P2SF_API_TOKEN='...'
python3 scripts/check_experiment_readiness.py \
  --config experiments/config/models.custom.json \
  --freeze-config experiments/config/freeze.custom.json \
  --models custom-model --scope corpus --allow-unfrozen --probe-completion
```

Start with one pipeline and one repetition before freezing a full run. Detailed instructions are in [Adding a model or provider](docs/ADDING_MODELS.md).

## Evidence packaging

Rendered prompts are not duplicated for all 7,590 publication cells because they account for most of the raw 3 GB run tree. They are deterministically regenerated from the included source, benchmark workspace, freeze, method, and seed. This Git repository retains every manifest and score record needed to regenerate and audit the reported statistics.

Model responses, generated submissions, validator reports, and M5 transcripts are preserved separately for a versioned GitHub Release or Zenodo deposit. The untouched raw run tree will be deposited separately, with its DOI or release URL and checksum added here before publication.

## Important interpretation rules

- M0--M2 produce direct Argo outputs and do not define G3, G4, G6-Exec, G6-Assert, or an end-to-end pass. Those outcomes are **not applicable**, not failures.
- The 110-instance pooled estimate is the headline result; split labels remain available for sensitivity analysis.
- The SINTEF M5 run used an older M5 image/prompt version than the two DeepInfra runs, so cross-provider M5 comparisons are descriptive.
- Provider-billed SINTEF cost was unavailable and is represented as missing, not zero.
- The M2-versus-M4 comparison is a bundled method-level sensitivity analysis, not an isolated causal estimate of the IR stage.

## License and citation

Code is released under the [MIT License](LICENSE). Benchmark source material retains its documented source license and attribution; see [data licensing](DATA_LICENSE.md) and `benchmark/source/`. Citation metadata is in [CITATION.cff](CITATION.cff).

