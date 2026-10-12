# Final evaluation data report

Headline estimates pool all 110 pipelines. Split labels remain in the run- and instance-level exports for sensitivity analysis.

## Batch validation

- Primary cells: 5,940/5,940.
- Confirmatory ablation cells: 1,650/1,650.
- Validation errors: 0.
- Retried infrastructure attempts retained for audit: 24.

## Primary outcomes (instance-macro means, %)

| Model | Method | Public executable validity | Semantic success | Node F1 | Edge F1 |
|---|---:|---:|---:|---:|---:|
| DeepSeek-V4.1-Flash | m0 | -- | -- | 0.000 | 0.000 |
| DeepSeek-V4.1-Flash | m1 | -- | -- | 0.000 | 0.000 |
| DeepSeek-V4.1-Flash | m2 | -- | -- | 0.958 | 0.862 |
| DeepSeek-V4.1-Flash | m3 | 15.2 | 0.3 | 0.958 | 0.931 |
| DeepSeek-V4.1-Flash | m4 | 75.2 | 0.9 | 0.916 | 0.888 |
| DeepSeek-V4.1-Flash | m5 | 56.4 | 0.9 | 0.939 | 0.902 |
| Qwen3-Coder-480B | m0 | -- | -- | 0.000 | 0.000 |
| Qwen3-Coder-480B | m1 | -- | -- | 0.000 | 0.000 |
| Qwen3-Coder-480B | m2 | -- | -- | 0.955 | 0.704 |
| Qwen3-Coder-480B | m3 | 7.3 | 0.0 | 0.980 | 0.847 |
| Qwen3-Coder-480B | m4 | 60.9 | 0.9 | 0.980 | 0.950 |
| Qwen3-Coder-480B | m5 | 1.5 | 0.0 | 0.502 | 0.466 |
| Qwen3.8-27B (SINTEF) | m0 | -- | -- | 0.000 | 0.000 |
| Qwen3.8-27B (SINTEF) | m1 | -- | -- | 0.000 | 0.000 |
| Qwen3.8-27B (SINTEF) | m2 | -- | -- | 0.680 | 0.577 |
| Qwen3.8-27B (SINTEF) | m3 | 0.9 | 0.0 | 0.018 | 0.006 |
| Qwen3.8-27B (SINTEF) | m4 | 7.9 | 0.0 | 0.587 | 0.561 |
| Qwen3.8-27B (SINTEF) | m5 | 16.4 | 0.3 | 0.612 | 0.591 |

Direct-Argo methods (M0--M2) have no end-to-end value because their output contract does not define G3, G4, or G6. Their applicable gate, grounding, graph, compilation, and efficiency results remain in the CSV and JSON exports.

## Confirmatory ablations (Qwen3-Coder-480B, pooled 110)

| Condition | Executable validity | Semantic success | Calls/run | Tokens/run |
|---|---:|---:|---:|---:|
| a1_no_contracts | 60.6 | 0.0 | 3.08 | 111505 |
| a2_no_policies | 54.5 | 0.3 | 3.15 | 117411 |
| a3_no_g5_repair_feedback | 62.7 | 0.0 | 3.00 | 119665 |
| a5_no_repair | 7.3 | 0.0 | 1.00 | 39119 |
| a6_unstructured_diagnostics | 60.3 | 0.3 | 3.00 | 118314 |
| m4_reference | 60.9 | 0.9 | 3.00 | 118706 |

### Paired ablation effects

Differences are condition minus the frozen v21 M4 reference.

| Condition | Metric | Difference | 95% BCa CI | Holm p |
|---|---|---:|---:|---:|
| a1_no_contracts | executable_valid | -0.3 pp | [-6.4, +5.8] | 1 |
| a1_no_contracts | semantic_success | -0.9 pp | [-5.5, +0.0] | 1 |
| a2_no_policies | executable_valid | -6.4 pp | [-13.0, +0.3] | 0.2644 |
| a2_no_policies | semantic_success | -0.6 pp | [-4.8, +0.0] | 1 |
| a3_no_g5_repair_feedback | executable_valid | +1.8 pp | [-4.2, +7.3] | 1 |
| a3_no_g5_repair_feedback | semantic_success | -0.9 pp | [-6.4, +0.0] | 1 |
| a5_no_repair | executable_valid | -53.6 pp | [-60.9, -47.0] | 0.0005 |
| a5_no_repair | semantic_success | -0.9 pp | [-5.5, +0.0] | 1 |
| a6_unstructured_diagnostics | executable_valid | -0.6 pp | [-6.7, +5.2] | 1 |
| a6_unstructured_diagnostics | semantic_success | -0.6 pp | [-3.6, +0.0] | 1 |
