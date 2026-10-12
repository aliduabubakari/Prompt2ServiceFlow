# Experiment assets

- `config/` contains the immutable freezes and model definitions used by the paper, plus a custom-provider template.
- `m5/` contains the agent/proxy source and the exact v2.1.8 build contexts used by the DeepInfra publication runs.
- `tools/bin/` contains the workspace compile and validation command wrappers.

Generated workspaces and new run outputs are intentionally gitignored. Build them locally from the benchmark and retain each batch summary if a run must be resumed.

Published result records are under `results/paper/`, separate from new experiments.

