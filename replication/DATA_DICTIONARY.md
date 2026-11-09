# Data dictionary

`results/paper/` preserves the original publication analysis and minimal records.
Do not overwrite its original costs or attempt counts to match revised tables.
The detailed archive adds final artifacts, reports and M5 proxy/transcript logs.
`results/regenerated/` contains derived, reproducible outputs and is not evidence
of original generation.

The accounting audit exports:

- `recorded_calls`: original method-specific counter; for M5 includes failed API responses.
- `successful_completions`: saved HTTP-200 responses for M5; M3/M4 ledger completions.
- `trace_successful_messages`: accepted usage-bearing assistant-message witnesses.
- `successful_completions_lower_bound`: maximum of proxy and accepted-message witnesses per run.
- `recorded_cost_usd`: original mixed-basis estimator, retained for provenance.
- `standardized_cost_usd`: common undiscounted model-specific rates.
- `proxy_log_incomplete`: missing/malformed evidence detected by the audit.
- `agent_steps`, `overrun`: turn-end count and whether it exceeds 12.
- `step12_inferred_executable_valid`: trace-based artifact-invariance inference;
  not a result of a new execution under a strict controller.

JSON audit files include input hashes, malformed-line diagnostics and the exact
post-cutoff tool commands used by the sensitivity audit. Provider usage can
include cached input tokens; do not add reasoning tokens to completions again.

The post-hoc archive uses exact content-addressed objects plus a separate path
map; historical records are not path-rewritten. Recorded MISSING pins remain
absences, not missing downloads. Revised pass status means every fixed role-
associated held-out predicate passed under profile 38.1 with profile conformance;
it is not the earlier frozen semantic score or a general domain-correctness claim.
