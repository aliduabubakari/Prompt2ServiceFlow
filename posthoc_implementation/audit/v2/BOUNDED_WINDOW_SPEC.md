# Original bounded-window workflow under a clarified v2 public profile

Package: `2.0.0-candidate.3`; audit protocol: `7.0.0`.
Profile: `bounded-window-1`, in `bounded_window_profile.json`.

## Scope and changes from v1

This stage targets the original six-step
`extension/building_energy_window_aggregation` workflow, not the previous CSV
round-trip substitute. It retains the original reference/model IR's service
choices, bindings, parameter labels, artifact identities, and dependency
edges. Actual input payloads flow through six service implementations:

1. Read bound JSONL measurements and the CSV registry.
2. Validate public batch bounds, identifiers, registry membership, and numeric fields.
3. Sort and deduplicate measurements.
4. Assign measurements to bounded windows.
5. Compute energy, demand, and power-factor metrics.
6. Publish actual CSV results and an integrity/audit manifest.

The public task, generic catalog profiles, and fixture configuration do not
fully determine all numerical semantics. Therefore the following rules are
**new explicit v2 choices**, not claims about the original private answers.
Old G6-Assert scores are neither recalculated nor replaced in this run.
Original public gates, including Argo validity, are not remeasured here.

The previous coverage scan has one known error in an unrelated satellite M5
artifact (`from_` instead of `from`). This protocol permits that exact reviewed
parent diagnostic, but rejects additional unreviewed planner errors. It does
not change that artifact or mark the original coverage report error-free.

## Public execution rules

- Use the active public fixture's `window_size_minutes`. In the supplied
  fixture this is 30 minutes; it takes precedence over the source's broad
  hourly/daily description **for this declared v2 condition only**.
- Require explicit timezone-aware batch start/end with start < end and a
  positive integer window size. Normalize timestamps to UTC. Never use the
  current wall clock or silently invent a missing value.
- Treat intervals as `[start, end)`, including a record exactly at the start
  and excluding one exactly at the batch end. Anchor consecutive fixed windows
  at batch start, truncating a final partial window at batch end.
- Treat `energy_kwh` as **interval energy**, not a cumulative meter counter.
  Sum eligible interval energy per building and window. This interpretation
  must not be represented as known original benchmark semantics.
- Normalize and validate the declared measurement fields. Energy and demand
  must be finite/nonnegative; power factor must be within 0..1. Every record,
  including one outside batch bounds, must satisfy input validation.
- Registry building IDs must be unique and non-empty; demand limits must be
  finite and positive. Reject unknown building IDs rather than discard them.
- Deduplicate by meter ID and normalized timestamp. Collapse records equal
  over the declared identity/measurement fields; reject conflicting values,
  including a different building, for the same key. Ignore unrelated annotation
  fields when comparing the declared measurement tuple.
- Deduplicate before filtering the batch interval. Track raw/unique/duplicate,
  in-range/out-of-range, and emitted-window counts. Do not emit empty windows.
- Group output by building and window. Building peak demand is the maximum,
  over observed timestamps in that window, of the sum of meter demands at
  that exact timestamp. No interpolation for missing observations is inferred.
- Mean power factor is the unweighted arithmetic mean of observed readings.
  Demand percentage is peak demand divided by the registry limit, times 100.
- Set `high_demand` when demand percentage is **greater than or equal to**
  `demand_threshold_pct`; set `low_power_factor` when mean power factor is
  **strictly less than** `power_factor_min`. Alert comparisons use decimal
  arithmetic over normalized numeric values, avoiding floating-point equality
  artifacts. Numeric output comparisons use 1e-9 relative/absolute tolerance.

Public fixture file roles/measurement field names are profile parameters.
There are no pipeline-ID/model-name switches, hardcoded output values,
private expectations, or native reference-program calls in the kernels.

## Original-IR interpretation limits

Only the six exact registered service IDs at version `1.0.0`, once each, are
supported in this profile. Their declared `operation_profile` labels must
match the named public source steps. These labels select a verified operation,
not arbitrary Python code or a pipeline-specific answer table.

One explicit `input_artifacts` bundle and the two exact `output_artifacts` /
`execution_report` outputs are required for each stage in this subset. Other
many-port arrangements remain unsupported even when the broad catalog allows
them. Only the declared `batch` provenance label and `true_streaming=false`
modality-policy fields are accepted; unknown behavioral parameters are not
silently ignored.

The adapter rejects malformed/conditional edges, unknown service versions,
branches, parallel groups, multi-producer ambiguity, undeclared writers,
secret-dependent invocations, non-JSON-shaped outputs, and missing fixture
links. It topologically orders the original control and actual data-producer
dependencies. It does not rename `from_`, infer missing model inputs, replace
service choices, or pick better intermediate attempts.

The original reference IR is a structural control, including its provenance
qualifications; it is not relabeled as a new public G0-valid model submission.
The public profile is an interpretation intervention even though saved IR
bytes are held fixed. Results must be described as **replay under clarified
v2 semantics**, not unchanged original semantic success.

## Output checks

Canonical bound outputs remain at `artifacts/<artifact_id>.json`. The actual
publisher emits `published/<intent_id>/window_metrics.csv` and
`published/<intent_id>/audit_manifest.json`. The bound final payload names these
files; neither the evaluator nor downstream tasks guess a filename.

The audit contains actual input SHA-256 values, canonical public-profile hash,
counts, and the published CSV hash. Applicable explicit public artifact schemas
are checked outside the sandbox. Unknown schema references are not fetched.

An independent checker uses exhaustive time partitions and decimal arithmetic,
rather than executor kernels or private assertions, to derive expected rows
from the actual public inputs. It compares every metric and alert in both the
bound final payload and actual CSV, execution states, counts, provenance,
profile identity, checksums, and applicable public output schemas.

## Fixed experiment

Reference controls use nine separately copied public-input scenarios:

| Scenario | Required behavior |
|---|---|
| Nominal | Complete computation matches the independent public-profile checker |
| Shuffled | Ordering changes do not change metrics |
| Identical duplicate | Collapse the duplicate, record its removal |
| Extra record | Consume the new measurement, including its demand/energy contribution |
| Changed energy | Change actual computed energy, not only counts/status |
| Boundary records | Include batch start, exclude batch end and a pre-start record |
| Conflicting duplicate | Reject at deduplication; never publish |
| Unknown building | Reject at validation; never publish |
| Missing energy field | Reject at validation; never publish |

Four negative controls must be detected: constant empty summary, wrong energy,
wrong demand flag, and missing publication. Numeric/flag mutations alter both
the final payload and CSV and update the CSV checksum, so detection cannot
depend only on a stale hash. These tests are development controls, not an
independent unseen test set for future repair tuned to their feedback.

Only after every reference control passes does the runner replay **all 27
original M3–M5 cells** for this pipeline across all three models/repetitions.
The nine-scenario maximum is 243 model-cell/scenario observations. Invalid,
missing, unsupported, or contradictory saved bindings remain visible.
An expected invalid-input rejection is checked separately from a transport
error and is not counted as successful normal execution.

All 54 original case cells remain in the ledger. The 27 direct-Argo M0–M2
cells are retained but not executed or converted into replacement IR.
No LLM client is constructed and no model inference is requested.

## Run and resume

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/run_v2_bounded_window.py
```

No API key is required. Add `--dry-run` for a read-only roster/profile preview.
The assistant performs synthetic checks and preflight only; the source-level
run and saved-model replay are left to the user.

Output: `audit/outputs/package_v2_bounded_window__<UTC time>__<id>/` with
`summary.md`, `run.json`, immutable input/code fingerprints, implementation
copies, derived public scenarios and their hashes, reference/model snapshots,
actual traces, all profile checks, and preserved negative-control artifacts.

If reference verification fails, saved-model replay does not start. The
reference failure is recorded rather than repeatedly tried until it passes.
Completed outcomes are kept on resume; an interrupted task gets a new attempt
directory. The original files, implementation, profile, and derived scenario
bytes must match:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_bounded_window.py \
  --resume /absolute/path/to/package_v2_bounded_window__YOUR_RUN
```

Return the printed `summary.md` path. A completed run means observations were
recorded with unchanged inputs, not that all model cells passed. V1, the DOI,
paper, original generated outputs, and all previous audit evidence remain
unchanged. No release, upload, or broad 110-pipeline rerun is performed here.
