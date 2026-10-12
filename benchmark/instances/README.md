# Benchmark Instances

Each pipeline instance will keep model-visible source/candidate files physically
separate from hidden gold bindings, fixtures, assertions, and review records.

Instances are authored in batches of five. Batch manifests live in `batches/`,
while split-specific instances live under `main/` and `validation/`.

The first locally complete vertical slice is:

- `main/airvisual_pipeline_lat_long_v1`;
- `main/data_quality_gate`.

See `docs/instance_authoring.md` for the required files and G0-G6 commands.
Cluster-backed G5 qualification remains a release step.
