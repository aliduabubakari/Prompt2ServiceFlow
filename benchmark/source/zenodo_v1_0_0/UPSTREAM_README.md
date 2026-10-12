# Pipeline Description Corpus (Descriptions Only)

This Zenodo package contains the structured natural-language workflow/pipeline descriptions used in the bounded self-repair studies.

## Contents

- `main_40/`: 40 main-study pipeline descriptions as `.txt` files.
- `validation_20/`: 20 held-out validation pipeline descriptions as `.txt` files.
- `inventories/`: source inventory CSV files for the main and validation splits.
- `manifest.csv`: one row per packaged pipeline, with metadata and description paths.

## Counts

- Main-study pipelines: 40
- Held-out validation pipelines: 20
- Total descriptions: 60

## Notes

The main split combines repository-derived and synthetic workflow specifications. Repository-derived specifications were reconstructed from public project documentation and workflow context; the original implementations were not intended as model input. Synthetic specifications were added to cover workflow topologies that are less common in the repository-derived subset.

The validation split contains prospective synthetic pipelines created after the main corpus and is intended for held-out validation or robustness analysis.

This description-only package omits the JSON machine-readable specifications to keep the file count below Zenodo's upload limit. The JSON specifications can be deposited separately as a companion archive if needed.
