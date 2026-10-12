# ServiceFlowCatalog

This directory will contain the versioned canonical service registry,
compatibility rules, model-visible instance candidate sets, and reusable Argo
WorkflowTemplates.

Catalog development begins after the source layer and core schemas are stable.

Catalog `0.1.0` uses contextual distractors as its core and a bounded pool of
eight reviewed supplemental services. The policy is documented in
`docs/catalog_curation_policy.md`. Candidate-set IDs are globally namespaced
before the immutable snapshot is written.
