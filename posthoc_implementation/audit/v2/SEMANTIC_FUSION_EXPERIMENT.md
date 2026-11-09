# Second family: public API/table join and routing

The reference-only census ranked family 562e2de209496bae first: three tasks share
seven local service descriptors. That ranking uses reference service coverage
and public implementation/input review flags, never model success or semantic
scores. No native reference program or private v1 assertion supplies a runtime,
model graph, input value or expected business result here.

## Public input review and limits

CRM sales enrichment and supplier-risk fusion each list three conceptual source
roles but expose only two input roles/files in their public manifests. The
third lookup/master source requires clarification; no empty source or invented
lookup is substituted. These tasks remain blocked for this implementation.

Support-profile context join supplies tickets, customer profiles and an actual
routing-policy JSON file. It is the one executable candidate selected by public
input completeness. Its task text mentions a subscription-plan lookup, while
the fixture provides routing policy. The v2 public supplement explicitly uses
that policy as the reference source and does not claim a missing plan lookup.
The task also mentions freshness without a clock or acceptance rule. The v2
profile does not invent freshness tests or claim complete v1 task equivalence.

This is a clarified development contract. Its join, field normalization,
priority/tier score, inclusive threshold, immediate categories and churn-priority
rule are stated in RELATIONAL_PUBLIC_CONTRACT.md and the profile JSON before
generation. These decisions are not described as recovery of hidden v1 intent.
The same supplement is visible to M3, M4 and Pi M5.

## Implementation and evaluation

The new seven-operation backend implements three independent ingestions, a
three-bundle validator, normalization, a many-record-to-unique-lookup join,
routing calculations and publication. Kernels use explicit input/field maps
and policy values rather than pipeline/model/artifact-name switches. Unsupported
versions, labels, nested record payloads, missing roles, ambiguous joins,
branches and guessed inputs stop execution. Independent ingestion state uses
distinct atomically published per-intent records so fan-in does not rely on a
shared mutable counter. No mock or schema-example fallback is allowed.

Each compiled task is self-contained and available to the existing Argo
compiler. Public G0–G5 and nominal G6-Exec checks retain the v27 documented
JSON/any compatibility and conservative shared compiler completion. Actual M3,
M4 and Pi M5 controllers, M4 repair budget three, M5 validator cap four, step
budget twelve and other registered limits remain unchanged. The earlier M5
budget-limited outcome is retained; this family is not an attempt to tune M5
until it passes. New code, configs, freezes, images and output records are
separate from the frozen window-family experiment.

A control graph is authored from the explicit public source steps/edges for
compiler verification only. It is never provided to the models. Private input
variants and the independent checker likewise remain outside method workspaces.
The checker uses exhaustive equality matching and Fraction arithmetic rather
than calling the implementation's hash join and Decimal kernels. It verifies
all joined field values, scores, Boolean decisions, row counts, CSV cells,
actual source/manifest/profile/CSV hashes and bound status/audit projections.
It requires the specific rejecting validator and no publication on invalid
inputs. Presence, telemetry and process success alone cannot pass.

Six positive variants cover nominal bytes, source reordering, changed priority,
changed policy, inclusive threshold equality and an additional primary record.
Three invalid variants cover duplicate lookup keys, missing join keys and
unknown priorities. Four mutants alter records, joins, scores or escalation
decisions while updating CSV and audit hashes consistently. All must be caught
before inference. These are development robustness checks, not nine independent
pipelines or untouched held-out tasks.

## Commands

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_fusion_experiment.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_experiment.py --controls-only
```

The control command requires no model token and makes zero LLM calls. It checks
the new runtime, public gates, numerical oracle, rejection behavior and four
mutants. After reviewing that result, Docker images and the default Qwen ×
M3/M4/M5 × seed 101 experiment can be run with:

```sh
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_experiment.py --build-m5-images
read -s "DEEPINFRA_TOKEN?DeepInfra API token: "
export DEEPINFRA_TOKEN
echo
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_experiment.py
```

The last command makes paid calls only after fresh controls pass. Full-design
mode adds the registered second model and two seeds, producing eighteen method
observations for this one task. Inspect the default run before spending on it.
Resume the same mode with `--resume /absolute/path/to/output`. The inherited
checkpoint protocol preserves valid failures and interrupted requests without
automatic paid resampling. Costs, tokens, prompts, raw responses, repair/tool
history, compilation edits, public reports and private checks are retained.

All v1 results, paper, deposit, earlier frozen code and the M5 failure remain
unchanged. A family with one executable task does not establish coverage or
semantic accuracy for all three nominal family members or the 110-task corpus.
