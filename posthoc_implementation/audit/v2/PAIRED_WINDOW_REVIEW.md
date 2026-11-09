# Review of paired v2 interpretation and binding repair

Reviewed 25 October 2026. Evidence:
`audit/outputs/package_v2_paired_window__20261025T092353Z__f5326d30/`.
Package `2.0.0-candidate.4`, audit protocol `9.0.0`; state `complete`.
No LLM calls, publication changes, or source-output replacement occurred.

## Integrity and controls

The review reverified all 49,367 input/code fingerprint entries and 636 saved
execution-artifact file hashes. All 21 existing model IR copies in the
compatibility condition retain their original bytes. The nine edited model
copies and the edited reference control can be reconstructed exactly by
applying their recorded additions to their original parsed IR.

All three controls passed nine scenarios each (27/27), and all 17 negative
controls were detected. The scenario checks include six positive computations
and three expected input rejections per control. The publication and repair
controls are derived mechanism controls, not additional original benchmark
pipelines or model outputs.

## Paired results for the fixed 27 IR cells

| Outcome | Compatibility interpretation | Interpretation plus binding repair |
|---|---:|---:|
| Evaluated; all nine profile scenarios passed | 1 | 2 |
| Unsupported input mapping | 8 | 11 |
| Checked contract/structure/dataflow violations | 12 | 6 |
| Unsupported execution contract | 0 | 2 |
| Missing saved IR | 6 | 6 |
| Total cells | 27 | 27 |

The increase in the mapping category is not a regression in executed behavior:
repairs clear missing status bindings and reveal remaining input problems.
Neither unsupported category represents an executed numeric semantic failure.
The 27 direct-Argo cells remain separately inventoried and unexecuted.

The successful saved compositions are:

- **DeepSeek M5 sample 2:** compatibility 9/9 and repair condition 9/9 with no
  IR edits. It binds the public source manifest, chooses the registered six
  services, and distinguishes primary, audit, and status outputs. Previously
  unsupported profile labels and multiple publication outputs can be handled
  by the new explicitly declared runtime interpretation.
- **DeepSeek M5 sample 1:** compatibility cannot locate the input manifest;
  the repair condition passes 9/9 after exactly one addition:
  `/artifacts/0/fixture_ref = fixtures/inputs/fixture.json`. No service,
  parameter, producer, existing artifact identity, or control edge changes.

Both original source manifests record `agent_step_budget_exhausted`. These
statuses remain unchanged. An executable saved intermediate/submission under
new conditions is not a successful original end-to-end agent run.

Only three model-condition records reached scenario execution: the two
conditions for sample 2 and the repair condition for sample 1. All passed
their six positive computations and three intended rejections. That is 27
model-condition/scenario observations, but only **two distinct saved cells**,
not 27 independently successful model submissions.

## What repair changed and what remains

Nine model copies received 68 JSON-pointer additions: four fixture links and
64 additions creating 32 required status artifacts and their 32 bindings.
Adding observability/status records usually did not restore computation,
because the original data input still could not be resolved.

After repair, 25 cells still do not reach execution:

- Six missing submissions.
- Six with unresolved checked contract, structure, or dataflow violations.
- Eleven with unresolved input mappings, including absent ingestor bindings,
  non-mapped or wrong existing fixture references, and external publisher
  inputs without links. Existing references were preserved rather than
  replaced by guessed files.
- Two outside the v2 status-output type/role contract (Qwen M4 sample 0 and
  SINTEF M5 sample 0). These remain runtime-compatibility findings, not claims
  that the original catalog forbids every such representation.

No failed computation was rerun until it passed. Missing submissions, unknown
services, ambiguous writers, and existing wrong references were not rebuilt.

## Root-cause conclusion and limits

This is direct evidence that some saved compositions can perform the intended
data processing once actual service semantics and output handling are
provided, and that one missing input link can prevent an otherwise executable
composition from running. It also shows why status completion alone is not a
general semantic repair strategy.

The interventions include an external profile override and newly declared
interval/window/aggregation semantics. They do not execute the original mock
compiler's behavior faithfully or demonstrate that the original held-out
G6-Assert oracle is wrong. The same service kernels are supplied to both
conditions; no new model-generated code or improved generation ability is
being measured. Original method outcomes and published semantic scores remain
intact. This exploratory one-workflow study cannot establish corpus-wide
semantic success or a ranking of M3–M5/models.

## Recommended next step

Freeze this completed mechanism study. Do not keep expanding repair rules on
this same pipeline simply to increase its pass count. Before broader replay,
perform a **corpus-wide static root-cause census** on the original 110
pipelines and fixed M3–M5 cells, without LLM calls or code execution:

1. Count missing/invalid IR, explicit catalog violations, writer/dataflow
   problems, and public input availability separately by model and method.
2. Separate generic catalog checks from this bounded-window adapter and its
   v2-only mapping rules. Do not apply the six-service roster or its profile
   labels as correctness requirements for other workflow families.
3. Inventory where public service contracts specify enough runtime behavior
   and where further numerical/input/output semantics must be declared.
4. Select the next service family using predeclared coverage/public-information
   criteria rather than which saved outputs appear likely to pass. Verify its
   references and negative controls before paired replay.

Keep direct-Argo M0–M2 availability/parse diagnostics separate from IR contract
counts; extending semantic replay to that route requires its own controlled
execution design. Report the current results as root-cause/mechanism evidence
for a v2 package, without changing the submitted paper's original measurements.
