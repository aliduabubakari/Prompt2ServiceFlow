# Relational public-input and diagnostic correction, v2.3

This is a new development condition following the valid, public-gate-blocked
M3/M4/M5 run `package_v2_fusion_v2_2__20261026T120856Z__00170920`.
Earlier freezes, runs, submitted-paper scores and the published v1 package
remain unchanged. A completed batch can still contain valid non-passes.

## Changes and limits

- The seven registered service descriptors now express the existing runtime
  requirement: one input per ordinary operation, three distinct inputs for
  the validator. The refined catalog has a new version, descriptor checksums,
  index checksum and workspace inventory. Input cardinalities are also
  explicit in the common public contract. No missing binding is filled in.
- Public compiler errors identify intent, service, port, expected count,
  observed count and source binding path. G3 lists all offending bindings.
  A missing derived manifest at G0 explains its input-binding cause, when
  present. Gate order, gate failures and M4's attempt-selection rule are kept.
- Two lossless JSON reading bundles contain allowlisted public information:
  `public_context.json` has task, candidates and execution contract;
  `public_interfaces.json` has the IR schema, candidate descriptors and
  artifact contracts. They must each fit below 48 KiB, or preflight stops.
  M5 is directed to these first. Individual public files remain available.
  M3/M4 receive the same facts in their existing inline prompt assembly.

The model still chooses the IR, services, bindings, artifacts, parameters and
control flow. No reference IR, private business output or altered evaluation
input enters the bundles, model prompts or repair feedback. Business rules,
input variants, independent assertions, common compiler completion, decoding
settings and controller budgets are unchanged. M5 has 12 steps, four validator
calls and the original token/time limits; M4 has three repair opportunities.
This public-information change may affect model behavior and must be reported
as a new experiment, not an unchanged-method replay or replacement v1 score.

The scope remains one clarified relational task. There is no claim of semantic
correctness across 110 pipelines. The reference input is the supplied routing
policy; subscription-plan lookup and freshness are not evaluated.

## Offline verification and user-run pilot

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python -m pytest -q tests/unit/test_v2_fusion_v2_3.py
.venv/bin/python scripts/run_v2_fusion_v2_3.py --dry-run
.venv/bin/python scripts/audit_v2_fusion_feedback.py
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_v2_3.py --controls-only
```

Tests include invalid-binding/schema controls, preserved gate precedence,
nonmutation of invalid IR, catalog checksums, lossless and size-bounded public
bundles, Pi's validator shim, isolated container-payload import and production
public execution. The controls-only run uses no LLM and must pass six positive
cases, three expected rejections and four semantic mutants before inference.

Build the new M5 images once. This uses Docker/build networks but makes no LLM
request; old v2.28.2 image tags cannot substitute for v2.28.3.

```sh
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_v2_3.py --build-m5-images
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_v2_3.py
```

The default paid pilot is Qwen-480B, M3/M4/M5, seed 101, on the one enabled
development task. It runs integration controls again before dispatching any
model call. Export `DEEPINFRA_TOKEN` in the same terminal; credentials are not
stored in this design or in the public bundle. Do not use `--full-design` yet.

For interruption recovery, pass `--resume` with the new output directory.
Completed cells are retained; an interrupted paid attempt is recorded rather
than automatically regenerated. Never resume a v2.2 run with the v2.3 runner.
