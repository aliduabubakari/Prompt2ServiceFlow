# File-backed execution-evidence replay: verified submission data

All original M3–M5 cells are retained. Complete-suite rates use all 330 runs per model/method. The original 797 public-valid cells remain eligible; 16 have unsupported dataflow and 781 were replayed. Their execution completion is a conditional diagnostic, not a new full-corpus method success rate.

| Model | Method | Replayed | Original / 330 | Before execution-evidence profile / 330 | File-backed profile / 330 | Execution-evidence assertion rate [95% BCa CI] |
|---|---|---:|---:|---:|---:|---:|
| deepinfra-deepseek-v4-1-flash | m3 | 50 | 1 | 12 | 38 | 11.5% [6.7, 17.9] |
| deepinfra-deepseek-v4-1-flash | m4 | 244 | 3 | 27 | 168 | 50.9% [41.8, 59.7] |
| deepinfra-deepseek-v4-1-flash | m5 | 186 | 3 | 29 | 116 | 35.2% [27.9, 42.7] |
| deepinfra-qwen3-coder-480b-turbo | m3 | 24 | 0 | 1 | 20 | 6.1% [2.7, 10.9] |
| deepinfra-qwen3-coder-480b-turbo | m4 | 190 | 3 | 21 | 127 | 38.5% [30.9, 46.7] |
| deepinfra-qwen3-coder-480b-turbo | m5 | 5 | 0 | 0 | 3 | 0.9% [0.0, 2.1] |
| sintef-qwen3-8-27b-nvfp4 | m3 | 3 | 0 | 1 | 1 | 0.3% [0.0, 0.9] |
| sintef-qwen3-8-27b-nvfp4 | m4 | 26 | 0 | 6 | 20 | 6.1% [3.3, 10.9] |
| sintef-qwen3-8-27b-nvfp4 | m5 | 53 | 1 | 5 | 41 | 12.4% [8.5, 17.0] |

Intervals resample 110 pipeline instances after averaging their three repetitions, using the existing paper analysis function. No new confirmatory significance claim is made.

```json
{
  "declared": 2970,
  "replayed": 781,
  "complete_execution": 781,
  "original_passes": 11,
  "literal_passes": 35,
  "role_passes": 534,
  "gained": 524,
  "lost": 1,
  "baseline_role_passes": 102,
  "gained_from_baseline": 432,
  "lost_from_baseline": 0,
  "literal_individual_checks": {
    "value_or_count_mismatch": 169,
    "missing_or_empty_output": 3467,
    "pass": 866,
    "unexpected_output_in_absence_check": 59,
    "missing_json_field": 93
  },
  "role_individual_checks": {
    "value_or_count_mismatch": 265,
    "missing_json_field": 643,
    "pass": 3436,
    "unexpected_output_in_absence_check": 87,
    "missing_or_empty_output": 168,
    "unresolved_output_role": 54,
    "json_path_container_type_mismatch": 1
  },
  "remaining_check_causes_by_compiler_state": {
    "value_or_count_mismatch / unchanged_unsupported_public_contract": 12,
    "missing_json_field / unchanged_unsupported_public_contract": 46,
    "missing_json_field / corrected_from_public_output_contract": 201,
    "value_or_count_mismatch / corrected_from_public_output_contract": 147,
    "unexpected_output_in_absence_check / corrected_from_public_output_contract": 55,
    "unexpected_output_in_absence_check / unchanged_valid_public_example": 25,
    "missing_or_empty_output / unresolved_writer": 168,
    "missing_json_field / unchanged_valid_public_example": 110,
    "missing_json_field / unchanged_no_concrete_schema": 255,
    "value_or_count_mismatch / unchanged_valid_public_example": 92,
    "value_or_count_mismatch / unresolved_writer": 3,
    "missing_json_field / unresolved_writer": 31,
    "unresolved_output_role / unresolved_writer": 54,
    "value_or_count_mismatch / unchanged_no_concrete_schema": 9,
    "unexpected_output_in_absence_check / unchanged_non_json_contract": 7,
    "value_or_count_mismatch / unchanged_non_json_contract": 2,
    "json_path_container_type_mismatch / corrected_from_public_output_contract": 1
  },
  "individual_checks_gained": 1985,
  "individual_checks_lost": 0,
  "former_format_error_outcomes": {
    "pass": 1612,
    "missing_json_field": 255
  },
  "reference_controls": 110,
  "reference_full_assertion_passes": 73,
  "states": {
    "not_replayed_original_public_invalid": 1432,
    "replayed": 781,
    "missing_saved_ir": 741,
    "blocked_execution_profile": 16
  },
  "positive_artifact_requirements": 2573,
  "positive_artifact_states": {
    "present_nonempty": 2369,
    "missing_or_empty": 164,
    "unresolved": 40
  },
  "required_json_present": 2354,
  "required_json_parseable": 2354,
  "llm_calls": 0,
  "runtime_executions": 0
}
```

Individual assertion pass rates and artifact presence have different denominators from complete-suite success. They describe failure modes and must not replace the complete-suite metric. The output requirements count unique positive reference paths per replayed cell/scenario; absence predicates remain in the assertion table. Unresolved paths remain visible.

The registered profile observes actual public files and declared predecessor artifacts, preserving per-producer versions. It supplements supported public mock outputs with execution evidence. It does not compute domain transformations or prove unrestricted task semantics. All 16 blocked dataflows remain in the full-roster denominator.

Held-out predicate values and operators are fixed. Model IR is byte-identical. This is a separately labeled post-hoc execution-profile intervention: public-only fixture views, producer-specific output storage, dependency scheduling and the common runtime changed. The 110 reference profile controls passed conformance; only 73 passed every held-out task assertion. References are not pooled with generated submissions. The original ablations have not been replayed under this profile.
