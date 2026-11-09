# Prompt2ServiceFlow v2 candidate

Local candidates: `2.0.0-candidate.1` (verified invocation executor) and
`2.0.0-candidate.2` (new complete local workflow-family controls).
Status: not published, tagged, pushed, or deposited.

The current next-stage CLI and its explicit scope are in
[FAMILY_CONTROLS.md](FAMILY_CONTROLS.md). Candidate.2 adds actual producer-to-
consumer execution, gate skipping, value-level semantic/negative controls,
and tested public-input prompt renderers. These are new mechanism-control
workflows, not replacements for original corpus pipelines or paper scores.
Candidate.1 files and completed evidence remain unchanged.

After completing the family controls, use the original-corpus static planner
in [COVERAGE_PLANNER.md](COVERAGE_PLANNER.md), audit protocol `6.0.0`. It maps
all 110 original workflows and all 5,940 saved M0–M5 model cells, preserves
separate IR/direct-Argo routes, and proposes implementation cohorts without
using semantic scores. It makes no model calls and executes no saved code.

The paper's v1 replication package and DOI
`10.5281/zenodo.23346818` remain unchanged. The original source baseline is
`d10a8be24a34f533c82d3f2c1e2ed7959f89a4b7`. Prior audit protocols v1–v3 are
diagnostic round numbers, not published package versions. This candidate's
first reference-control protocol is `4.0.0`.

## Implemented changes

1. Separate canonical artifact bindings from service-requested output
   locations. A CSV dataset cannot overwrite another port's metadata merely
   because the requested filenames match. Actual dataset/metadata contents
   and port identities remain distinct.
2. Treat absolute service output locations as contained logical container
   labels, never host write permissions. Record output mappings and hashes.
3. Build a public per-scenario fixture manifest and require explicit input
   links for execution. Missing mappings, unsupported upstream operations,
   unresolved paths, and missing logical time are not filled in by guessing.
4. Add synthetic regression tests and six fixed reference controls: the four
   CSV invocations that failed audit v3 plus the two previous positive controls.

The rules and compatibility boundary are documented in
[PUBLIC_EXECUTION_CONTRACT.md](PUBLIC_EXECUTION_CONTRACT.md).

## Run the reference controls

No API token is required:

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/run_v2_reference_controls.py
```

For a read-only roster preview, add `--dry-run`. To resume an interrupted run,
use the directory printed by this runner:

```zsh
caffeinate -ims .venv/bin/python -u scripts/run_v2_reference_controls.py \
  --resume /absolute/path/to/package_v2_controls__YOUR_RUN
```

The runner fingerprints the frozen baseline, v2 implementation and contract,
dependencies, tests, and public workspace files. Changed inputs or code cannot
silently resume an old condition. Recorded outcomes, including failures, are
retained; interrupted controls receive a new attempt directory. Outputs are
written under the ignored `audit/outputs/` directory.

The candidate currently reuses the unchanged audit v3 operation subset and
sandbox/replay utilities. These dependencies are fingerprinted and copied
into run evidence as appropriate. This folder alone is not yet a standalone
replication distribution; packaging is a separate release step.

## Verification completed

On 2026-10-24:

- 81 focused tests passed across earlier controls and the new v2 regressions.
- All six reference invocations passed public output schemas, output-location
  integrity checks, and changed-input checks.
- The five CSV invocations consumed an added input row (3 → 4).
- The retention control consumed a changed age (30 → 37).
- Frozen source/public input hashes remained unchanged. No LLM calls were made.

Evidence:

```text
audit/outputs/package_v2_controls__20261024T142626Z__1da13623/summary.md
audit/outputs/package_v2_controls__20261024T142626Z__1da13623/run.json
```

These results validate the narrow path-handling correction, not complete
workflow execution, model composition correctness, or G6-Assert success.

## Not changed or launched

- No original model output, reference IR, private assertion, public benchmark
  fixture, submitted score, paper text, prior audit run, or archive was edited.
- No new model generation, broad saved-output replay, release, or upload ran.
- The M3/M4 prompt exposure correction is not retroactively applied. A future
  v2 generation condition must render the public fixture/binding information
  into actual prompts, with a separate immutable protocol and new outputs.
- Upstream computation, branching, typed CSV schemas, and a full semantic
  evaluation remain separate work. Unsupported operations still fail closed.

Next: review this contract and six-control evidence, then prepare a separately
versioned replay of applicable saved invocations. Any subsequent generation
or repair study must be labeled as v2 evidence rather than merged into v1.

The targeted replay is now prepared under audit protocol `4.1.0`; see
[MODEL_REPLAY.md](MODEL_REPLAY.md) for its fixed 221-invocation cohort, full
original-cell coverage ledger, execution CLI, and resume instructions. It
uses the unchanged candidate executor that passed the reference controls.
