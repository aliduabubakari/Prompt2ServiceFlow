# Protocol 16: offline audit after the restricted enum repair

The model patch resolved eight schema errors using eight replace operations and
preserved the public identity. This is evidence for a bounded schema-feedback
repair, not semantic improvement. Before another generation call, inspect the
saved original candidate and patched candidate under the same public contracts.

## What the script does

- Verifies the completed generation and repair fingerprints, all saved response
  files, the public workspace inventory, and the exact schema.
- Reapplies the saved model patch in memory using the restricted patch checker,
  confirming that it reproduces the saved candidate without any extra edits.
- Runs the existing corpus-census static inspector on both candidates. Retains
  schema, catalog, dataflow, literal-type, and context findings separately.
  Counts non-schema contract/dataflow findings before and after, and checks
  whether those diagnostics changed.
- Inventories explicit artifact fixture links, bound external artifacts,
  multiple writers, and bindings reading/writing the same artifact identity.
  These last observations are review cues, not invented catalog requirements.
  In particular, no explicit external binding does not prove a service has no
  implicit source; a shared input/output identity is not by itself a proven
  dependency cycle. The public contracts and runtime need separate review.
- Writes detailed before/after analyses and an immutable input fingerprint in
  a new output directory. A successful audit can identify a blocked candidate.

There are zero API calls, zero workflow executions, no compilation, no hidden
assertion scoring, and no automatic rewiring or fixture assignment. No token
environment variable is required. The script does not load reference IR as a
replacement composition or treat a model's validation expectations as results.
Static applicability/sufficiency signals are not semantic failures or passes.

## Command

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/audit_v2_candidate_contracts.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_candidate_contracts.py
```

The first command verifies inputs without creating a run. The second creates
`audit/outputs/package_v2_candidate_contracts__.../summary.md`. Review this report
before deciding on a general contract/graph repair or revising the public input
and runtime specification. Preserve v1 and all original failure denominators.
