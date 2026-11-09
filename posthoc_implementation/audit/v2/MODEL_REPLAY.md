# V2 targeted saved-invocation replay

Package candidate: `2.0.0-candidate.1`.
Audit protocol: `4.1.0`.
No LLM calls, new generation, or repair of saved compositions.

## Fixed inputs and passing reference gate

The cohort comes from the completed v3 inventory:

```text
audit/outputs/executor_replay_v3__20261024T135118Z__4dba6147/
```

The executor is exactly the v2 candidate verified by the user's six-control run:

```text
audit/outputs/package_v2_controls__20261024T145930Z__1bec7e27/
```

Before replay, the runner requires all six declared reference controls to pass
and verifies their implementation/input fingerprints against the current code.
It also verifies the v3 inventory's source files, previously missing files,
and public workspace bytes. An old missing IR appearing, or a changed saved
IR/configuration, requires a new versioned condition rather than silent reuse.

No original benchmark file, v1 code, model prompt, model binding, score, or
private assertion is edited. The new public manifest describes input
availability; it is not used to guess a missing binding.

## Target selection and coverage

Selection uses exact service/version support, **not previous outcomes**.
Every model invocation identified in v3 for the three registered services at
version `1.0.0` is retained, including previous failures and blocked cases:

| Previous v3 state | Target invocations |
|---|---:|
| Unsupported operation/input provision | 167 |
| Invalid binding or unsupported input mapping | 31 |
| Executed | 12 |
| Execution error | 11 |
| Total | 221 |

The targets include Qwen-480B v21, DeepSeek-Flash v22, and SINTEF v19 M3–M5
outputs. The original 2,970-cell model ledger is retained alongside the replay,
including 741 cells without final IR and 18 with invalid IR under the earlier
diagnostic parser. Out-of-scope service/version occurrences are also retained
as coverage information; they are not relabeled as executed or silently
removed from the original design.

These are service invocations, not 221 distinct pipelines or independent
experimental repetitions. M0–M2 do not use this same IR invocation interface
and are not converted or assigned new comparable scores.

## What changes and what does not?

The same unchanged saved input/output/parameter bindings are interpreted by
the verified v2 adapter. Requested output locations and canonical bound
artifacts are separated according to `PUBLIC_EXECUTION_CONTRACT.md`. This
avoids cross-port overwrites without substituting hidden expected values.

The runner still refuses to supply missing fixtures, invent upstream results,
drop contradictory required columns, relax output schemas, choose a better
intermediate IR, or introduce private reference scenario definitions. Missing
links and unsupported operations remain visible even though they are targets.

Applicable invocations execute under the network-disabled sandbox. The
runner checks actual public output schemas, complete port-to-artifact output
mapping, contained requested locations, matching output bytes, and the
limited changed-input age/count relations. Each target is paired with its
original v3 state and reason.

An execution error is a recorded observation, not automatically a proven
model semantic error. Interpret input-interface limitations, adapter limits,
and contradictory bindings separately. A successful invocation does not
prove correct service selection or whole-pipeline semantics.

## Run

No API token is required:

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/run_v2_model_replay.py
```

For the read-only preflight/roster count:

```zsh
.venv/bin/python -u scripts/run_v2_model_replay.py --dry-run
```

Selection is fixed in `model_replay.json` and the verified inventory. There
are no method/model/pipeline filtering flags that could accidentally turn the
run into a success-selected subset. Any new selection requires a new protocol.

## Outputs and resume

The runner creates a unique directory:

```text
audit/outputs/package_v2_model_replay__<UTC time>__<id>/
```

Evidence includes:

- `summary.md`: paired prior/new states by model and method, limited
  changed-input outcomes, and the retained original coverage counts.
- `run.json`, `roster.json`: fixed target identities, original source paths,
  model/method/sample identities, prior states/reasons, and new observations.
- `coverage_ledger.json`: every original M3–M5 model cell, including those
  without usable IR or without supported service invocations.
- `input_sha256.json`: parent evidence and current implementation/input hashes.
- `implementation/`: the exact new runner/config/tests and reused dependencies,
  preserved with their relative paths.
- `verification.txt`: synthetic selection, safety, integrity, and replay tests.
- `targets/`: public manifests, unchanged derived adapter specifications,
  original/changed execution snapshots, output mappings, hashes, and checks.

Resume with the printed directory:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_model_replay.py \
  --resume /absolute/path/to/package_v2_model_replay__YOUR_RUN
```

Inputs, code, fixed cohort, and the original-cell ledger must match. Recorded
outcomes, including failures, are skipped. Interrupted targets get a fresh
attempt directory and do not overwrite partial evidence. Runner errors are
reported separately and produce `complete_with_errors`; investigate them
before creating a separately labeled retry. `complete` means all targets
were recorded with unchanged inputs, not that all targets passed.

## Verification during preparation

94 focused tests passed across all existing controls and the new replay.
The new synthetic replay checks that the output-path collision is resolved
while original IR bytes remain unchanged, missing fixture references remain
missing, and genuinely absent required columns still cause rejection.
Integrity tests reject source changes, duplicate targets, and incomplete
output mapping. The dry run verified all 221 targets and the passing v2 gate.

The assistant has not launched the actual model replay. Return its printed
`summary.md` path for review after running it.

This is not a publication-scale generation run, a revised G6-Assert result,
or a change to the paper's v1 evidence. Full upstream computation, branching,
prompt exposure changes, and any subsequent generation/repair study remain
separate work.
