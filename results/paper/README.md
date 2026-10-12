# Packaged paper results

This directory contains the evidence used for the evaluation section.

- `analysis/` is the complete published table/statistics bundle.
- `batch_summaries/` declares all 7,590 completed primary and ablation cells.
- `runs/` contains each cell's manifest and, where applicable, score record, keyed by immutable run ID.
- `run_index.csv` maps every cell to its batch and manifest.
- `SHA256SUMS` verifies every packaged result file.

Rendered prompts are omitted because the frozen code and inputs regenerate them exactly and duplicating them adds roughly 0.8 GB. Full responses, generated artifacts, validator reports, and M5 transcripts are preserved for a versioned GitHub Release or Zenodo deposit rather than ordinary Git history.

See `docs/REPRODUCING_PAPER_RESULTS.md` for verification and regeneration commands.
