# Evaluation-final analysis bundle

This directory is the reproducible data source for `evaluation_final.tex`.
Headline estimates pool Main-40, Validation-20, and Extension-50 (110 pipeline
instances), while preserving split labels in every run- and instance-level
export.

## Completeness

- Primary experiment: 5,940/5,940 cells (3 models x 6 methods x 110 instances
  x 3 repetitions).
- Confirmatory ablation: 1,650/1,650 cells (5 conditions x 110 instances x 3
  repetitions).
- Invalid recorded observations: 0.
- Temporary ablation infrastructure attempts: 24; retained in the immutable
  audit trail and replaced by successful reruns of the same cells.

The exact batch identities, file hashes, freeze identifiers, method counts,
split counts, prompt versions, and validation warnings are in
`batch_validation.json`.

## Files

- `report.md` and `report.json`: compact human- and machine-readable summaries.
- `primary_run_level.csv`: all 5,940 primary observations.
- `primary_instance_level.csv`: three repetitions averaged within each primary
  model-method-instance cell.
- `primary_summary.csv`: pooled model-method estimates and 95% BCa intervals.
- `primary_split_sensitivity.csv`: Main, Validation, and Extension estimates.
- `primary_gate_summary.csv`: unconditional individual-gate pass rates.
- `primary_gate_survival.csv`: cumulative G0 through G6-Exec survival for
  M3--M5.
- `primary_paired_effects.csv`: planned M4-M3 and M4-M5 paired effects.
- `primary_failure_modes.csv`: recorded first-failing-gate counts.
- `ablation_run_level.csv`, `ablation_instance_level.csv`, and
  `ablation_summary.csv`: merged Main, Extension, and Validation ablation data.
- `ablation_paired_effects.csv`: each confirmatory condition paired with frozen
  v21 M4.
- `stage_removal_sensitivity.csv`: non-confirmatory M2-versus-M4 bundled-stage
  sensitivity.
- `posthoc_main_g6_assert.json`: deterministic Main-40 G6-Assert audit produced
  by scorer v1.2.1; no new LLM inference was used.
- `paper_update_notes.md`: changes required outside the evaluation section.

## Regeneration

From the repository root:

```bash
python3 scripts/rescore_main_semantic_assertions.py
python3 scripts/prepare_evaluation_final_results.py
```

The preparation script fails if a batch is incomplete, contains duplicate or
missing cells, points to a missing manifest, retains an invalid observation,
or does not match the frozen three-repetition design.

## Interpretation constraints

1. M0--M2 do not define G3, G4, G6-Exec, or G6-Assert. Their end-to-end and
   semantic outcomes are N/A, not zero.
2. M0 and M1 received only `task.md`; M2 used frozen candidate/catalog inputs.
   M2 is therefore catalog-grounded direct Argo, not an online retrieval run.
3. SINTEF provider-billed cost is unavailable and must not be recorded as
   zero.
4. SINTEF M5 used older image/prompt versions than DeepInfra M5. Cross-provider
   M5 comparisons are descriptive.
5. Ablation runs used four workers and the v21 reference used one. Do not make
   causal claims from their latency difference.
6. Semantic success is computed with fail-closed scorer v1.2.1. The previous
   scorer could treat a zero-assertion scenario-name mismatch as a pass.

