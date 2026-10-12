# Result artifacts and data dictionary

## Batch summaries

Each JSON file in `results/paper/batch_summaries/` declares its freeze, expected cells, seeds, model roster, execution settings, completed runs, and retained infrastructure attempts. `manifest_path` is repository-relative.

## Run records

Each directory in `results/paper/runs/` is named by its immutable `run_id`. The Git repository contains:

- `manifest.json`: identity, freeze, model, method, instance, usage, environment, and evaluation summary.
- `score.json`: public-gate and semantic/structural scoring for M3--M5 and the ablation conditions.

The manifest embeds the evaluation values used for M0--M2. Complete model responses, generated submissions, validator reports, and M5 tool traces are preserved outside Git for a versioned GitHub Release or Zenodo deposit. Their immutable run IDs match these directories.

## Analysis tables

- `primary_run_level.csv`: 5,940 individual observations.
- `primary_instance_level.csv`: repetitions averaged within model-method-instance.
- `primary_summary.csv`: pooled model-method estimates with intervals.
- `primary_split_sensitivity.csv`: estimates by corpus stratum.
- `primary_gate_summary.csv` and `primary_gate_survival.csv`: individual and cumulative gates.
- `primary_paired_effects.csv`: paired M4--M3 and M4--M5 effects.
- `ablation_run_level.csv`, `ablation_instance_level.csv`, `ablation_summary.csv`: merged ablation evidence.
- `ablation_paired_effects.csv`: confirmatory differences from v21 M4.
- `stage_removal_sensitivity.csv`: M2-versus-M4 method-level sensitivity.
- `primary_failure_modes.csv`: first-failing-gate counts.
- `report.json` and `report.md`: compact machine- and human-readable summaries.

Token fields include prompt, completion, reasoning, and total tokens where reported. Reasoning tokens are a subset of completion tokens for the frozen primary designs and must not be added to completion tokens a second time. Missing provider cost is represented as missing.

