# Generation Record

- corpus: Prompt2ServiceFlow Extension-50
- corpus version: extension_v1
- source type: synthetic, deterministic, provenance-marked
- generator: `scripts/create_extension_50_sources.py`
- generated content: public descriptions and reviewer companion source specifications
- prohibited content: hidden gold annotations, candidate labels, service bindings, ServiceFlowIR, runtime mocks, Argo outputs
- frozen baseline policy: Frozen-60 artifacts are not mutated
- streaming policy: true streaming is excluded; event/checkpoint/window cases are bounded batch workflows
