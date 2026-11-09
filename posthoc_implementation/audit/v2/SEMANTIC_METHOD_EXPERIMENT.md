# V2 experiment using the actual method controllers

This is a new development experiment. The original paper, v1 files, deposits,
scores and frozen audit records are unchanged. It does not recover the old
semantic-success scores. The first supported task is the reviewed bounded
window computation; broader service families still require implementations and
reviewed public numerical/input contracts.

## Methods and common changes

The existing Python M3 controller generates once. The existing M4 controller
generates, validates and repairs under B=3, retaining the best public-validator
state. The existing Pi M5 driver uses its file tools, twelve agent steps, three
idle continuations and four validator calls. Its wrapper, Pi package/version,
internal Docker network, proxy and token budget follow the existing protocol.
These are actual controllers, not three labels applied to one generation call.

Versioned adapter modules run those controller sources in independent module
namespaces. They do not edit or globally monkey-patch the old methods. All
methods receive the same public task, candidates, catalog, schemas, nominal
inputs, exact public metadata, registered operations, numerical/input contract
and compiler-completion policy. Old mock-runtime/source-identity instructions
are explicitly replaced in the v2 templates. These prompt changes apply across
methods, not to a particular model. No model-specific repair prompt is added.

The shared contract explicitly renders the existing bounded public fixture
previews for M3 generation and M4 repair. Pi M5 can inspect that same contract
and the original public files through its tools. Per-method presentation still
follows the existing prompt-versus-file interfaces; no claim of identical
serialized context is made. Full evaluation variants are never rendered.

The common compiler preserves service/parameter/input/control choices. It logs
raw IR and the declared conservative completion edits, writes a canonical IR,
and generates a real task per intent. Each task is self-contained, uses the
registered standard-library service kernels, and is available to the original
Argo compiler without host-only modules or unmounted JSON sidecars. Data edges
must be explicitly present in the model's control graph; the compiler never
silently adds them. Unknown service versions, operation labels, runtime choices,
input semantics or extra parameters stop compilation. There is no mock fallback.

The old public G0–G5/G6-Exec validator is reused with one declared G3 correction:
public any ports accept json/object computation bundles. Other mismatches,
required ports/parameters, artifact schemas, grounding, policy checks and
cardinality remain enforced. The real-backend scope and exact bookkeeping are
also checked publicly. Gate results are versioned v2 results, not unchanged v1
gate measurements. Argo compilation/lint is checked; no cluster deployment is
claimed. The Docker image has Python kernels; no evaluator or private fixtures
are included in its public-tool payload.

M4 and M5 receive only those public diagnostics and nominal execution/schema
outcomes. After each method terminates, its canonical IR is committed and
evaluated on six positive input variants and three invalid-input variants.
The independent numerical oracle, published CSV/hash/source checks, bound
status/audit projections and exact failure reasons are evaluated outside the
method workspace. Expected answers and evaluation variants never enter repair
feedback. Inputs already inspected during audit development are not described
as untouched held-out generalization.

## Design and interpretation

Default: Qwen, one task, M3/M4/M5, seed 101: three new method observations.
The registered full development design adds DeepSeek and seeds 202/303: eighteen
observations. Nine input cases per composition are robustness checks, not nine
independent pipelines. This study can test integration and repeated generation
under explicit contracts, not establish a semantic rate over all 110 tasks.
M0–M2 are not included in this IR study. They require a separate direct-Argo
execution route with equivalent business evaluation before a semantic comparison.

All methods use temperature .2, top_p 1 and the same per-request output budget.
Seeds and decoding requests are logged; server support/determinism is not
assumed. The Pi proxy injects the same settings and records complete request/
response wire data, retaining standard reasoning and tool fields unchanged.
M3/M4 also retain raw responses; reasoning is never substituted for final text.
Token counts, per-stage usage, latency, controller/validator calls, repairs,
public gate results, business checks, compilation edits, image identities and
invalid/provider attempts are retained. No current price is assumed; dollar
costs stay unavailable without a registered dated price schedule.

The freeze binds code, method source hashes, model settings, public contract,
input files, scenario roster and prior evidence. M5 images use separate v2 tags
and record built image identities. Base image tags follow the inherited image
recipe; recorded image IDs identify actual execution, rather than promising
byte-identical future rebuilds. Image IDs must match when resuming a batch.

Before paid calls, the runner requires the separate v2 images and executes a
fresh integration control using the previously validated v2 model composition.
All public gates, six business cases, three specific rejections and four
business-output mutants must pass. Failed controls stop the batch before
inference. This control is not counted as another model observation.

## User-run commands

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_method_experiment.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_method_experiment.py --controls-only
```

The control command needs no model token and makes zero LLM calls. After it
passes, prepare the separate v2 images (Docker must be running):

```sh
caffeinate -ims .venv/bin/python -u scripts/run_v2_method_experiment.py --build-m5-images
```

Then run the three-method development experiment. This command makes paid calls:

```sh
read -s "DEEPINFRA_TOKEN?DeepInfra API token: "
export DEEPINFRA_TOKEN
echo
caffeinate -ims .venv/bin/python -u scripts/run_v2_method_experiment.py
```

For the eighteen-cell design, add `--full-design`. First inspect the default
experiment's public gate failures, semantic outcomes and usage. No success
threshold is selected to obtain a preferred paper result.

A batch resumes using the same mode and `--resume /absolute/path/to/output`.
Completed checkpoints are verified and reused. Interrupted paid attempts are
retained as unknown/invalid without automatic redispatch; failures do not lead
to silent repeated sampling. New attempts require a separately identified batch
and must retain earlier evidence. A complete ledger does not imply all methods
passed or all infrastructure observations were valid.
