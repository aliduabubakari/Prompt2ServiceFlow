# Static saved-output eligibility for the CSV/PostgreSQL control subset

This phase retains all 108 original declared cells for file_arrival_watcher
and val_csv_to_warehouse_daily: three original models, M0-M5, three samples.
The two tasks retain their original Main/Validation labels. They are inspected
development data here, not untouched held-out validation. No source is selected
by prior success, and a missing artifact or failed original method stays in
coverage with its original status.

## Prerequisites and provenance

The completed PostgreSQL control run must pass both case gates. Its original
input manifest is verified, as is the separate review-time output seal of all
546 control evidence files. That output seal is not presented as having been
captured at execution time. The original census's two task checkpoints and
every saved artifact hash are checked. Original raw files, code, data, method
freezes, published scores and deposits remain unchanged.

## Checks and interpretation

M3-M5 are read as bounded YAML/JSON IR. Schema checks use a pinned schema with
only local references. YAML aliases and executable tags are not interpreted.
The audit checks service/version roster, required input/output ports and
types, explicit fixture/resource links, source CSV identity, required columns,
parameters, target-table identifiers/write modes, metadata flow, intent lists,
producers/consumers, dependencies/cycles and the supported missing-file gate.
Secret-dependent bindings and unsupported transport/branch/parallel choices
remain blockers. It never infers a missing link from a unique available file,
a named system or a reference graph. No expression, template, SQL, program or
workflow from the saved output is executed.

Diagnostics separate saved-structure issues, public-input context, limits of
the new backend subset and runtime interpretation. A catalog-valid feature
such as upsert or SFTP can be outside this controlled implementation; that
finding is not automatically an LLM error. New v2 fixture/header assumptions
are not silently imposed as claims about undocumented v1 task intent.

Two static views are reported. A strict static contract match has no recorded
findings. A runtime-intervention-only candidate has only findings that would
require an explicitly declared change to runtime interpretation or resource
binding. The latter is hypothetical: no mock runtime is changed, resource
rebound, template resolved or missing business choice inserted. A cell with
other blockers remains blocked even in that view.

Neither view certifies execution readiness. The control family does not yet
have a verified M3/M4/M5 IR-to-PostgreSQL execution adapter. Every row therefore
has execution_ready=false and semantic_outcome=not_measured. Compatible-looking
parameters are prerequisites to a later verified adapter, not semantic passes.

M0-M2 retain their direct-Argo route. The audit inventories YAML resource and
script/container-template structure only. It does not run their scripts,
convert them to reference IR or score them using the IR contract. They need a
separate equivalent business execution route before semantic comparison.
These parser/shape classifications can differ from the older census's broader
inventory criteria; neither set is a new executable-validity or semantic score.

## Outputs

- summary.md: availability, static states, model/method counts and overlapping
  finding codes. Each model/method has six declared cells (two tasks × samples).
- eligibility.json / eligibility.csv: all 108 original identities, statuses,
  routes, artifact hashes and detailed findings. Raw script bodies are not
  copied into reports or executed.
- aggregate.json, run.json, input_sha256.json, per-cell hashed checkpoints and
  verification.txt: reproducibility and integrity evidence.

## CLI

From the semantic-audit workspace:

```sh
.venv/bin/python scripts/audit_v2_csv_replay_eligibility.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_csv_replay_eligibility.py
```

No API key, Docker daemon, PostgreSQL server or model server is needed. Only
synthetic static unit checks and saved-file inspection are performed. The
command prints the new output directory, one line per cell and summary path.
On interruption, completed cell hashes and identities must still match:

```sh
caffeinate -ims .venv/bin/python -u scripts/audit_v2_csv_replay_eligibility.py \
  --resume /absolute/path/to/the/eligibility/output-directory
```

This is not a replay or generation command. A later study must declare and
verify the execution adapter, resource interpretation and equivalent business
checks before running compatible saved outputs. It must preserve failures and
ineligible cells and remain separate from v1 paper scores.
