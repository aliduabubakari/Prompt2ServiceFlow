# Experiment protocol

## Corpus and experimental unit

The corpus contains 110 pipeline instances: Main-40, Validation-20, and Extension-50. The pipeline instance is the statistical unit. Every primary model-method-instance cell was repeated with seeds 101, 202, and 303. Repetitions are averaged within an instance before macro estimates, confidence intervals, and paired tests are calculated.

The completed primary design is:

```text
110 instances × 3 models × 6 methods × 3 repetitions = 5,940 observations
```

The completed confirmatory ablation is:

```text
110 instances × 1 model × 5 conditions × 3 repetitions = 1,650 observations
```

## Frozen primary runs

| Freeze | Model | Provider |
|---|---|---|
| `freeze.sintef.v19.json` | `qwen3.8:27b-nvfp4` | self-hosted SINTEF endpoint |
| `freeze.deepinfra.v21.json` | Qwen3-Coder-480B-A35B-Instruct-Turbo | DeepInfra |
| `freeze.deepinfra.v22.json` | DeepSeek-V4.1-Flash | DeepInfra |

Each freeze records the endpoint metadata, model name, decoding parameters, context window, repair and agent budgets, corpus size, execution order, and expected cell count. Tokens are supplied only through environment variables.

## Frozen ablation

The v24 ablation uses Qwen3-Coder-480B and compares five predeclared conditions with the frozen v21 M4 reference:

- `a1_no_contracts`: hides contract context and details.
- `a2_no_policies`: hides lifecycle and policy context.
- `a3_no_g5_repair_feedback`: keeps G5 evaluation but removes its diagnostic detail from repair prompts.
- `a5_no_repair`: uses the corresponding M3 pre-repair pipeline.
- `a6_unstructured_diagnostics`: exposes only failing gate identities during repair.

M2 versus M4 is reported separately as a non-confirmatory bundled stage-removal sensitivity comparison.

## Validity and resume policy

- A batch is complete only when every declared cell has one valid recorded observation.
- Rate limits, endpoint outages, model-template failures, and container failures are recorded as infrastructure attempts and remain pending until the same immutable batch is resumed.
- A model’s failure to satisfy a method gate is a scientific outcome and is not rerun merely to obtain a pass.
- Gold data is never included in a visible workspace. The leakage preflight runs before inference.
- Validation-set reruns require the explicit runner flag and should be justified in the audit record.

## Analysis

The analysis uses instance-macro means, 95% BCa bootstrap intervals over instances, paired sign-flip/permutation tests, and Holm correction for the five confirmatory ablation contrasts. Split labels are retained even where the headline estimate pools all 110 instances.

