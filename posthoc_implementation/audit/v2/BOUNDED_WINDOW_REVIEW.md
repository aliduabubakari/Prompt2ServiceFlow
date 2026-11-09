# Review of bounded-window controls and saved-output replay

Reviewed 25 October 2026. Evidence:
`audit/outputs/package_v2_bounded_window__20261024T222338Z__907d9dfc/`.
This note interprets completed evidence; it changes no experiment inputs,
saved outputs, original scores, or published package.

## What completed

The run recorded all 27 selected M3–M5 cells and retained the separate 27
direct-Argo cells. Its state is `complete`, with zero LLM calls and unchanged
source inputs. Complete means the planned observations were recorded.

The reference passed all nine profile scenarios: six successful computations
and three expected input rejections. All four negative controls were detected,
including coordinated changes to the final payload and published CSV with
updated checksums. These checks support the new executor and checker for the
declared profile. They do not independently validate the original G6-Assert
oracle or the full corpus, and they are development controls, not unseen tests.

## Saved model results

| Recorded outcome | Cells |
|---|---:|
| Unsupported profile or binding | 20 |
| Missing saved IR at the inventoried submission path | 6 |
| Invalid or unavailable saved input: duplicate/unmatched identifiers | 1 |
| Reached scenario execution | 0 |

Among the 20 unsupported records, the first rejection was:

| First rejection | Cells |
|---|---:|
| Input/output arrangement differs from the adapter's exact one-bundle/two-output requirement | 9 |
| Operation-profile string differs from the adapter's accepted step label | 10 |
| Service roster differs from the exact six registered services | 1 |

These are first blockers, not a complete inventory of defects. The displayed
`0/9` for these records means no successful checks were recorded; it must not
be described as nine executed semantic failures per cell. No model cell
produced a numeric result for comparison in this run.

## Why interpretation needs care

The public catalog (`benchmark/catalog/snapshots/0.3.3/services/`) permits
optional, many-cardinality `input_artifacts`, many-cardinality
`output_artifacts`, and requires an `execution_report`. Its required string
`operation_profile` has no enumerated accepted values. The new adapter instead
requires one explicit input bundle, exactly one data output and one status
output, and exact source-step profile labels.

Thus the replay exposes an adapter-coverage boundary as well as saved-output
problems. A different label alone is not proof of an incorrect computation.
Omitting an optional input is not, by itself, a violation of the old catalog,
although this executor cannot locate data without an explicit input link.
Conversely, missing required reports, ambiguous writers, nonexistent service
IDs, and unresolved actual input paths need their own contract/dataflow review.

Static inspection of the 21 existing YAML files found seven registered
ingestors without an input binding. Only two cells explicitly bind that
ingestor to the active fixture manifest file: DeepSeek M5 sample 2 and SINTEF
M5 sample 0. Other references include missing links, directories, nonexistent
bundle paths, or a raw measurement file instead of the expected manifest.
This is a path/binding observation, not an execution pass/fail score. Even the
two explicit-manifest cells have additional adapter/interface blockers.

## Recommended next step

Do not launch a broad replay or buy more generations yet. First build a
read-only, all-blocker compatibility report for these 27 cells, checking the
actual public catalog, producer/consumer links, required outputs, profile
configuration, and fixture paths independently. Keep unsupported semantics
separate from demonstrably invalid catalog bindings and missing submissions.

Use that report to specify a new, versioned compatibility condition before
execution. Define general handling of catalog-supported multiple artifacts
and public profile configurations; do not silently equate arbitrary labels
or invent how an unspecified operation behaves. Reuse the reference and
negative-control gate, then replay the entire fixed cohort and retain every
outcome, including cells that remain unsupported.

Any added fixture binding, changed service choice, repaired writer, or changed
parameter value belongs in a separately labeled deterministic-repair condition
with an explicit edit log. It cannot count as unchanged saved-output replay.
Both stages can use saved outputs without LLM calls. A changed prompt would
require a separate generation experiment.

The present result establishes that this reference can compute and respond to
input changes under explicit v2 rules. It does not establish that low original
semantic success is entirely a model problem, entirely an evaluator problem,
or resolved by the current executor. Published G6-Assert scores remain intact.
