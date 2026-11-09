# Paired v2 interpretation and conservative binding repair

Package `2.0.0-candidate.4`; audit protocol `9.0.0`.
This is an exploratory mechanism study for the fixed original
`extension/building_energy_window_aggregation` cohort. It is not a new
110-pipeline benchmark score or a change to the submitted paper's results.

## Fixed inputs and paired conditions

The completed protocol-8 compatibility audit fixes the original 54-cell
ledger. Both conditions retain all 27 M3–M5 cells across three models and
three repetitions, including missing submissions and budget-exhausted agent
outcomes. The 27 direct-Argo M0–M2 cells remain separately labeled and are not
converted or executed. No model calls or generation/repair APIs are used.

Both conditions use the same nine public scenarios, finite-window kernels,
numeric rules, independent decimal oracle, and original method statuses.
The nine checks comprise six positive computations and three expected input
rejections. Eligibility uses checked structure/contracts and explicit
semantics, never previous semantic scores or desired outputs.

### Compatibility interpretation

Original saved YAML bytes, services, bindings, parameter strings, and edges
remain intact. An **external v2 execution profile explicitly overrides the
undocumented original operation-profile strings** when dispatching each of
the six registered service identities at version 1.0.0. This is a declared
interpretation intervention, not evidence that arbitrary labels are synonyms
or that the original service already implemented these semantics. Every plan
and runtime trace retains both the original label and external operation.
Other unknown behavior parameters, streaming, secrets, unregistered services,
and nonlinear control remain unsupported.

The supported output contract is deliberately bounded:

- Each computation consumes one explicitly bound JSON bundle and produces
  one primary JSON bundle (`role: intermediate` or `output`) plus its required
  `execution_report` status.
- The publisher may also bind one additional `output_artifacts` artifact
  when that artifact explicitly has `role: report` and type `json`/`object`.
  With two data-port bindings, the primary must explicitly have `role: output`.
- The primary retains the computed metrics, counts, and published paths. The
  additional report receives the actual publication audit object, not a copy
  of the computation payload. Status outputs remain separate typed records.
- Audit projections cannot feed computation. Multiple ambiguous computation
  outputs/inputs, multiple reports, contradictory writers, or unclear roles
  remain unsupported. No behavior is chosen by model/pipeline/artifact names.

This handles a specified subset of the catalog's many-artifact port, not every
possible many-cardinality arrangement. A private dispatch view verifies graph
constraints while removing only the separately checked audit projection and
selecting external operations. It does not replace the saved IR. The evaluator
selects the primary using declared roles and checks additional bound reports
against the actual publication audit and statuses against execution success.
Applicable public schemas are checked; no remote schema is fetched.

### Conservative deterministic binding repair

Use the same runtime interpretation, then apply only two rules to copies:

1. Add a missing `fixture_ref` to an already uniquely bound external ingestor
   artifact with explicit input role and compatible JSON/object/any type, if
   exactly one contained public JSON manifest has the declared input roles,
   window configuration fields, and existing contained data files. Do not
   replace any existing reference, invent an unbound input/artifact, or choose
   between multiple manifests. The new link uses the active-scenario mapping.
2. Add a missing required `execution_report` binding and a new typed status
   artifact only when the public descriptor explicitly requires this single
   status output and no existing status artifact for that producer needs
   reconciliation. New identifiers are deterministic with collision handling.

Before repairs, reject checked structure/dataflow or catalog violations beyond
the rule's missing-required-status exception. Revalidate after repairs. Unknown
services, ambiguous writers, undeclared artifacts, conflicting statuses, wrong
existing paths, incompatible types, and missing submissions are not repaired.
An unsupported input remains unsupported even if status outputs were added.

Every edit is an explicit JSON-pointer `add` operation with its exact value,
rule, and public evidence. Applying the log to the original parsed IR must
reconstruct the effective IR. Rules are idempotent. No parameter, service,
producer, control edge, or existing artifact identity is changed. Both original
and effective copies/hashes are saved, alongside skipped-rule decisions.

## Control gate before any saved-model replay

All three controls must pass:

| Control | Condition | Purpose |
|---|---|---|
| Original structural reference | Compatibility | Check the original six-stage IR under the declared external runtime |
| Reference with explicit publication/report roles | Compatibility | Check distinct primary, audit, and status projections |
| Same projection control with source link and six statuses removed | Binding repair | Check the two repair rules, with exactly 13 logged additions |

The latter two are **derived mechanism controls**, not unchanged gold model
outputs. Controls consume actual public inputs. They do not run native gold
programs or use private assertions as a repair oracle. Each control runs all
nine scenarios. Each must detect wrong energy, wrong alert, constant empty
metrics, missing publication, and wrong bound status; the two projection
controls must also detect a wrong bound audit. Total: 27 scenario checks and
17 negative controls. A failed gate stops saved-model replay; resume does not
rerun a completed failed control until it happens to pass.

Only after this gate may both conditions attempt the fixed model cohort:
54 condition records and at most 486 model/scenario checks. Missing, invalid,
unsupported, and runtime failures stay in the ledger. No executed result is
inferred for an unexecuted cell. An absence of static findings is not claimed
as a full public-gate pass.

## Run

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/run_v2_paired_window.py
```

No API token is required. `--dry-run` only checks immutable parents, the fixed
roster, and derived-scenario hashes; it creates no run or model replay. Synthetic
unit tests run automatically before source-level controls. The assistant's
preparation validation uses synthetic measurement data and original IR shape;
the source-level experiment remains for the user to run.

The output folder is `audit/outputs/package_v2_paired_window__.../` with
`summary.md`, `run.json`, `paired_results.json`, `paired_results.csv`, input/code
fingerprints, source copies, diagnostics, plans, edit logs, actual execution
snapshots, and negative controls. Original agent statuses are retained in the
summary/CSV even if a saved output succeeds under the new condition.

Resume only this exact study/code/input condition:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_paired_window.py \
  --resume /absolute/path/to/package_v2_paired_window__YOUR_RUN
```

Completed records are retained; an interrupted unfinished record gets a new
attempt directory. Original source, profile, code, parent evidence, and public
scenario bytes must be unchanged. Modifying any of them requires a new study,
not silently resuming the old one. Final integrity checks include derived
scenario files. A completed run means observations were recorded, not that
all cells passed. No publication, Git push, DOI update, or paper edit occurs.

## How to interpret the paired results

Report computation checks, expected rejections, unavailable/unsupported cases,
and repair counts separately. Compare paired identities and describe runtime
interpretation and binding-repair effects as distinct interventions. Do not
rename these results original G6-Assert scores or use this single workflow to
estimate corpus-wide semantic success. Conditions and controls were designed
after inspecting earlier diagnostics, so they are exploratory rather than
unseen confirmatory evidence. Broader service families still need their own
public semantics and controls before receiving new semantic scores.
