# Static compatibility audit before another replay

Protocol `8.0.0`, package `2.0.0-candidate.3`. This adds diagnostics, not a new
executor or repaired method. The parent is the completed bounded-window run
`package_v2_bounded_window__20261024T222338Z__907d9dfc`.

## Fixed scope

Retain all 54 cells for `extension/building_energy_window_aggregation` from
the parent ledger. Inspect all 27 M3–M5 cells, including missing/invalid saved
submissions, across the three original models and repetitions. Keep the other
27 M0–M2 cells as a separate, unexecuted direct-Argo route. Selection does not
depend on earlier scores or which cells seem easiest to recover.

The audit verifies parent fingerprints, then checks independent constraints
rather than stopping at the first adapter rejection. It reads the saved IR,
the frozen **public workspace catalog**, the IR schema, and explicitly bound
public fixture manifests. It reads no private assertion files or native
reference programs. It makes no API/model calls and runs no saved scripts,
workflows, containers, conditions, or service implementations. The runner's
own synthetic unit tests run before inspection.

## Meaning of the findings

| Category | Interpretation |
|---|---|
| `saved_structure` | JSON/YAML shape, IR schema, duplicate identifiers, or unmatched intent/binding rosters |
| `public_catalog` | Checked service/version is absent, required port/parameter is missing, port is unknown, single port is repeated, or explicit parameter type/enum/bounds is violated |
| `dataflow` | Undeclared artifacts, inconsistent writers, missing producer bindings, bad edge endpoints, or cycles |
| `v2_input_mapping` | Missing or unusable explicit input/fixture link under the new v2 mapping convention |
| `adapter_limit` | Exact profile/roster/port arrangement or other behavior required by the narrow adapter, beyond the broad catalog |
| `public_semantics_unspecified` | Catalog parameter values are not enumerated, so arbitrary profile strings cannot be judged semantically from that declaration alone |
| `inspection_error` | Local catalog/integrity or inspection failure; not an error attributed to the model |

Counts are given both per finding and per affected cell. A cell can have many
findings in several categories. Category cell counts overlap. Required
`execution_report` omissions are catalog findings. An omitted optional input
is not automatically a catalog violation. Multiple data artifacts on a
many-cardinality port are not automatically a catalog violation. An arbitrary
profile string is not silently mapped to a different configured operation.

Fixture links are checked against the **active nominal public fixture** using
the existing v2 `fixtures/inputs/<relative>` or
`fixtures/scenarios/<label>/<relative>` mapping. The label is not used to pin
replays to nominal data. No file is guessed or substituted. A valid bundle
must be a JSON object with the declared input roles and existing contained
files. Raw data files/directories are not treated as bundle manifests.
This convention is a v2 execution requirement, not a retroactive v1 rule.

The checks cover this bounded-window compatibility subset. They are not the
full G0–G6 validator: catalog snapshot provenance, all type/consumer/policy
relationships, nonlinear control semantics, artifact value conformance, and
semantic correctness are not certified. JSON-schema findings report locations
and validator names without copying possible secret instance values. All
schema references used for IR validation are local fragments; nothing is
fetched from the network. Public catalog descriptors are checked against the
public workspace's recorded file hashes.

## Run

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/audit_v2_bounded_compatibility.py
```

No token is required. Use `--dry-run` to verify the parent and fixed roster
without inspecting model cells or creating output. Each full invocation
creates a unique `audit/outputs/package_v2_bounded_compatibility__.../` folder:

- `summary.md`: category counts and the complete 27-cell table.
- `findings.json`: every located finding, source paths, and external-input checks.
- `findings.csv`: flat, filterable findings (missing submissions are in the ledger/summary, not invented findings).
- `counts.json`: affected-cell and finding counts.
- `run.json`: all 54 original cells, environment, status, and zero-call/execution/repair declarations.
- `input_sha256.json`, `implementation/`, `verification.txt`: immutable input/code fingerprints, diagnostic source copies, and synthetic-test results.

A missing saved file or malformed model output is recorded; it does not halt
the other inspections. An inspection/integrity error is surfaced separately
and makes the final state `complete_with_errors` or `inputs_changed`. A
completed audit means diagnostics were recorded, not that workflows passed.
The tool does not resume an interrupted scan; rerunning creates a new scan
without overwriting earlier evidence.

## Decision after inspection

Review all blockers together. Define general, catalog-supported compatibility
rules before another execution condition; do not add per-model/per-pipeline
exceptions just to pass these outputs. Preserve unsupported configurations
when their meaning is not public. Any added input link, changed service or
parameter, or repaired writer needs a separate deterministic-repair condition
and edit log. Neither compatibility interpretation nor repair replaces the
submitted paper's original G6-Assert scores. No publication, source, saved
output, or previous evidence is modified by this diagnostic.
