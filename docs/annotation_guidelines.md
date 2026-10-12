# Annotation Guidelines

Status: initial scaffold

The detailed guidelines will be frozen during the six-instance pilot.

## Initial Rules

1. A workflow task is not automatically a service.
2. Every source step must be mapped to one or more service intents, represented
   as orchestration, marked as a no-op/placeholder, or marked unresolvable.
3. Split a source step only when it contains independently reusable
   capabilities with distinct contracts or effects.
4. Keep branch, join, fan-out, schedule, and dependency semantics in the
   control-flow layer.
5. Record whether each annotation is explicit, strongly inferred, weakly
   inferred, or unresolvable.
6. LLM-produced annotations are candidates until reviewed and validated.
7. The model-visible candidate catalog must never include gold correctness
   labels.

The first worked examples will be AirVisual and Data Quality Gate.

