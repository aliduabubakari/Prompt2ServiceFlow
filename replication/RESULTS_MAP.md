# Result-to-evidence map

| Artifact | Evidence | Reproduction |
|---|---|---|
| Table 4 | Separate corpus-analysis repository | External owner; not a framework-release blocker |
| Table 5 | Frozen visible-input policies, prompts, configs | Inspect method manifests and implementation |
| Table 6 original public column | 5,940 primary manifests | original mode; primary_summary.csv |
| Table 6 original assertions | Frozen original scores plus Main-40 scorer 1.2.1 audit | original mode for statistics; posthoc mode for pass counts in table6.csv/.tex |
| Table 6 revised assertions | Sealed profile-38.1 package, 2,970 checkpoints | posthoc mode; table6.csv/.tex with BCa intervals |
| Paired assertion transitions and missing outputs | Original assertion observations joined to sealed replay outcomes by cell identity | posthoc mode; paired_assertions.csv and run_level.csv |
| M2–M4 selected gates | Recorded G0, G1, G2, G5 statuses | original mode; stage_removal_sensitivity.csv and primary_run_level.csv |
| Table 7 | Curated graphs/bindings and original scores | original mode; primary_summary.csv |
| Table 8 | Final retained M4 evaluation gate vectors | original mode; primary_gate_survival.csv |
| Table 9 | 1,650 ablation cells and frozen M4 reference | original mode; ablation_summary/paired_effects.csv |
| Table 10 | Usage ledgers, proxy logs, frozen prices | accounting mode; table10.csv/.tex |
| M5 step-12 sensitivity | 990 traces and final artifacts | accounting mode; step12_sensitivity.csv/audit.json |
| Revised profile controls | 110 sealed reference checkpoints | posthoc mode; reference_controls.csv |

All mode combines the three offline modes, without runtime execution or model
calls. All 330 observations per model/method remain in output-assertion denominators.
The original Main scenario-name correction and revised mock profile remain separate.
