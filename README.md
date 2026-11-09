# Prompt2ServiceFlow: implementation and paper reproduction

Release 1.1.0 reproduces the framework results and the paired assertion audit.
The reviewed 14-page PDF is pinned by SHA-256 in
`replication/RELEASE_MANIFEST.json`. This snapshot contains the current working
implementation; it does not assert that this exact source revision generated
all historical outputs.

## Start here

Python 3.11+ is required. From this repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[analysis]'
python scripts/reproduce_submission_results.py --mode original
```

This reproduces and checks the original published statistical bundle from all
5,940 primary and 1,650 ablation records. It needs no credentials and does not
execute generated workflows. The three Table 6 outcome columns and paired transitions are reproduced below.

For updated accounting, fetch and verify the pinned detailed archive (or use
`--archive /path/to/Prompt2ServiceFlow-paper-runs-v1.tar.gz` for an offline copy):

```sh
python scripts/fetch_replication_evidence.py --output ../evidence
```

Then run:

```sh
python scripts/reproduce_submission_results.py --mode accounting --evidence-root ../evidence
```

This audits successful responses, API attempts, standardized prices, missing
logs and step-12 sensitivity, and writes `results/regenerated/submission/`.
It produces Table 10 CSV and a TeX fragment, including the Qwen-27B lower-bound
annotation. Failed requests remain operational overhead; original provider cost
estimates are preserved separately.

Download the [profile 38.1 evidence archive](https://github.com/aliduabubakari/Prompt2ServiceFlow/releases/download/v1.1.0/Prompt2ServiceFlow-posthoc-38.1-evidence.tar.gz)
from the versioned GitHub release. Verify and extract it:

```sh
python scripts/extract_posthoc_evidence.py --archive /path/to/Prompt2ServiceFlow-posthoc-38.1-evidence.tar.gz --output ../posthoc-evidence
```

Then run:

```sh
python scripts/reproduce_submission_results.py --mode posthoc --posthoc-root ../posthoc-evidence
```

This verifies 117,589 recorded input pins, the sealed outputs and all 2,970
checkpoints, then regenerates `posthoc/table6.csv`, `posthoc/table6.tex`,
and `posthoc/paired_assertions.csv`. Table 6 separates original executable
validity, original G6-Assert, and the revised G6-Assert profile. The paired
audit reports gains, reversals, original missing outputs and the literal-path
sensitivity under the revised runtime.
The revised compiler/evaluator source is under `posthoc_implementation/`.
It is a public file-backed mock-execution profile, not a retroactive original
model score or real domain-service execution. No generated program runs during
saved-results verification. Table 4's corpus classifications are maintained in
a separate corpus repository and are outside this framework package's scope.

To regenerate all saved results after both evidence archives are extracted:

```sh
python scripts/reproduce_submission_results.py --mode all --evidence-root ../evidence --posthoc-root ../posthoc-evidence
```

## Three reproduction routes

1. **Saved-results analysis:** the commands above; no model calls or generated-code execution.
2. **Deterministic re-execution:** public validation and held-out assertion checks
   on retained submissions, requiring reconstructed public workspaces and the
   supported sandbox. Both the original Main-40 audit and the revised profile are preserved separately;
   a fresh relocated runtime replay remains a separate qualification. See
   [execution profiles](replication/EXECUTION_PROFILE.md).
3. **New stochastic generation:** use the existing readiness, pilot and corpus
   instructions in `docs/`. Provider access, Docker and the relevant runtime
   tools are needed. New output identity is not guaranteed. Create new configs
   and output directories; never overwrite publication records.

## Code and evidence

GitHub contains implementation, benchmark references, prompts, schemas, tests,
analysis code and compact result records. Zenodo preserves versioned detailed
model outputs, final submissions, validation reports, transcripts and proxy
records. Code snapshots and reproduction tools accompany archival releases.
The [original Zenodo deposit](https://doi.org/10.5281/zenodo.23346818)
contains the original detailed run records. This release adds the accounting
audit and revised-profile evidence, with the replay archive linked above.
The [ServiceComposeBench-ETL v1.0.0 release](https://github.com/aliduabubakari/ServiceComposeBench-ETL/releases/tag/v1.0.0)
provides the standalone benchmark. This repository preserves the frozen
experiment inputs and configurations.

- [Results map](replication/RESULTS_MAP.md)
- [Protocol and accounting](replication/EXPERIMENT_PROTOCOL.md)
- [Data dictionary](replication/DATA_DICTIONARY.md)
- [Release readiness and missing inputs](replication/RELEASE_READINESS.md)

The benchmark has 110 instances (40 Main, 20 Validation, 50 Extension). M0--M2
lack the runtime contract for full end-to-end validation; N/A is not zero.
M4 uses explicit Python-client decoding settings; M5's Pi requests omit
configured temperature, top-p and seed. M4--M5 comparisons concern complete
implemented configurations. SINTEF monetary cost is unavailable, not zero.

Code is MIT licensed; preserve third-party benchmark attribution under
`DATA_LICENSE.md`. No secrets should be stored in configs or command arguments.
