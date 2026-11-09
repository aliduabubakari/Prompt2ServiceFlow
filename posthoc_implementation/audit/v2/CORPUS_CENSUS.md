# Corpus-wide static root-cause census

Audit protocol `10.0.0`, package `2.0.0-candidate.4`. This adds diagnostics to
the isolated v2 audit workspace, not a new runtime, repair rule, or model run.

## Scope and immutable selection

The original protocol-6 coverage ledger fixes **110 pipelines and 5,940
cells**: three original models, M0–M5, and three repetitions. The complete
case/model/method/repetition cross-product must match, not only the total.
There are 2,970 IR cells (M3–M5) and 2,970 direct-Argo cells (M0–M2). The
original Main-40, Validation-20, and Extension-50 labels remain in per-cell
records; the headline census pools the 110 pipelines. No cell is selected by
previous semantic outcomes or the existence of a convenient saved output.

The completed paired-window study and original coverage fingerprints are
verified before scanning. The old scanner's exact known satellite `from_`
inspection error is retained in prior evidence. This census handles malformed
edges as findings; it neither rewrites that output nor edits the old report.

## What is checked

| Category | Meaning |
|---|---|
| `saved_structure` | YAML/JSON/schema problems, duplicate identities, mismatched intent/binding rosters |
| `catalog_contract` | Explicit service/version, required ports/parameters/secrets, cardinality, parameter constraints, unknown names, and intent/binding artifact-set disagreements |
| `dataflow` | Missing artifacts/producers, contradictory writers, malformed or unknown edge endpoints, and dependency cycles |
| `frozen_type_rule` | Artifact/port data types are not literally equal under the original validator's rule, including `any` |
| `input_context` | No explicit fixture link, missing public files, or runtime mapping that needs review |
| `execution_context` | Runtime templates, merge/branch/gate/parallel semantics, external resources, credentials, or destructive-operation review |
| `runtime_semantics` | Public descriptor/schema signals that need human review before defining executable behavior |
| `inspection_error` | Dataset/catalog/checksum/tooling problem, kept separate from model errors |

The categories overlap. Counts are provided per affected cell and per finding.
The state `inspected` means a file was processed; it does not mean its IR is valid.
Checked hard findings (structure/catalog/dataflow) are separate from literal
type-rule findings and context needs. These are a documented static subset,
not a rerun of all G0–G6 checks and not numerical root-cause attribution.

There are **no bounded-window service-roster, label, role, input-bundle, or
output-projection requirements** in this census. An optional input can be
omitted, and many-cardinality ports can bind several artifacts. Non-enumerated
profile strings are public-semantic review signals rather than invalid labels.
Declared multi-producer artifacts are flagged for merge semantics; contradictory
writers are kept as dataflow findings. Malformed `from_` is not renamed.

The frozen validator compares port/artifact type strings exactly, even `any`.
The census reproduces that literal comparison **in its own category** rather
than asserting that such a pair cannot compute correctly. Explicit parameter
type/enum/bounds/pattern checks are additional declaration checks; unresolved
runtime template values are deferred to `execution_context`, not evaluated.
Secret binding names may be checked, but secret values/instance values are
not copied into finding text.

## Public input and schema inspection

Each frozen public workspace is checked against its builder file inventory.
Builder exclusions and declared scenarios are retained as data evidence. For
each bound external artifact, the census records both:

1. Whether its literal contained path exists as a file/directory.
2. Whether `fixtures/inputs/<relative>` or
   `fixtures/scenarios/<label>/<relative>` resolves to files across the public
   active scenarios under the existing audit convention.

Those observations are separate. No mapping is chosen or repaired. An external
resource or workflow parameter may need runtime context rather than a fixture,
and a missing optional `fixture_ref` is not automatically an old contract
violation. No fixture data values are read to derive expected task answers.

Artifact schemas are inspected only for local presence, syntax, hashes, and
reference-resolution needs. No external reference is fetched; actual produced
artifact values are not validated or synthesized. Public catalog descriptors
are checked against their workspace hashes. Service semantics inventories
retain variants of a service/version across snapshots and record descriptive
signals such as opaque object parameters, `any` ports, unenumerated profiles,
generic reviewed-operation wording, and declared implementation/image metadata.
These signals do **not** automatically certify or disprove semantic sufficiency
or the existence/correctness of an implementation inside an image.

## References, families, and selection for later review

The 110 gold IR files are read only as structural reference controls for
public contract and implementation planning. No private assertion, native gold
program, hidden expected value, or gold replacement binding is used to repair
or score a model output. Model diagnostics and reference diagnostics stay
separate.

Reference families group workflows with the same set of service/version pairs.
They are service-roster groups, not proof that the workflows share numerical
semantics. Descriptor variants remain available in `service_inventory.json`.
The immutable ranking order is:

1. Reference inspection/checked-contract/literal-type review count.
2. Reference network/credential/destructive review count.
3. Reference input-context review count.
4. Descending number of reference pipelines covered by the shared roster.
5. Number of unique service/version pairs.
6. Public artifact-schema reference-review count.
7. Stable roster fingerprint.

No model diagnostic, saved-output availability, model status, semantic score,
or expected improvement enters this ranking. It is a review proposal, not
execution authorization or a claim that a group is ready for replay.

## Run and resume

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/run_v2_corpus_census.py
```

No API token is required. This makes zero LLM calls, executes zero saved
workflows/code/conditions, applies zero repairs, and produces no semantic
scores. The runner runs its own synthetic static-analysis tests. `--dry-run`
verifies prior evidence, the complete original roster, and public file pins;
it does not inspect model cells or create output.

Each run creates `audit/outputs/package_v2_corpus_census__.../`. Progress is
printed once per pipeline, with all 54 original cells retained. Results:

- `summary.md`: pooled model/method counts and reference-only review groups.
- `aggregate_census.json`: complete route/state/category counts.
- `saved_cell_census.json`: every original cell and located findings.
- `cells.csv`: all 5,940 cells, including missing/invalid files, with route,
  original status, original stratum, and category flags (IR only).
- `model_method.csv`: category counts with explicit model/method/route denominators.
- `findings.csv`: filterable IR findings, with original strata/status retained.
- `reference_census.json`, `service_inventory.json`, `reference_families.json`:
  separate reference evidence, descriptor signals/variants, and review proposals.
- `cases/.../census.json`: public workspace context and complete per-case results.
- `run.json`, `input_sha256.json`, `implementation/`, `verification.txt`:
  fixed source ledger, environment, immutable input/code pins, checkpoint
  hashes, diagnostic source copies, and test results.

Missing or malformed saved output does not stop other cells. Local inspection
errors are recorded separately and yield `complete_with_errors`; changed
inputs yield `inputs_changed`. A completed scan means diagnostics are recorded,
not that workflows passed. Exact resume checks code/design/source fingerprints
and hashes/source identities of completed per-case checkpoint files, both on
resume and before final aggregation:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_corpus_census.py \
  --resume /absolute/path/to/package_v2_corpus_census__YOUR_RUN
```

No original code, data, model output, previous evidence, paper, GitHub release,
or DOI deposit is changed. The census can guide the next controlled replay
family; it cannot itself establish semantic correctness, explain every low
G6-Assert score, or replace the submitted results.
