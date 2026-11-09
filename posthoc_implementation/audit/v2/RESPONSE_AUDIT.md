# Saved-response audit before extraction repair or new generation

Audit protocol `11.0.0`; package `2.0.0-candidate.4`. This read-only diagnostic
uses completed corpus-census checkpoints, not a new selection based on scores.

## Fixed selection and provenance

The original census fixes 5,940 cells and 741 missing final IR files. Select
**all 471** of those missing-IR cells with original status `parse_error`, across
all models, workflows, and repetitions. Preserve the full 741-cell missing-IR
context ledger; budget exhaustion, LLM errors, and unknown statuses are not
silently reclassified as parse failures. No earlier successful intermediate
artifact is substituted for the original final submission.

The audit reads the original manifest and `responses/<stage>.txt` files.
It pins their exact bytes/presence, current diagnostic code, and parent
evidence before inspection, then checks them again at completion. This pins
the located saved files for this audit; it does not invent historical raw API
payloads that were not retained. It reads no private assertions or native
reference programs, constructs no LLM client, and executes no saved code.

## Attempt order and metadata

Recorded `usage.per_stage` order is authoritative when unique and complete.
Every recorded stage is retained, including a missing response file. Initial
M3 generation and all recorded M4 parse/main repair attempts remain distinct.
If metadata are missing, duplicated, or inconsistent with the saved response
files, filenames provide inspection hints only; the terminal call is marked
unresolved rather than guessed from modification time or apparent quality.
Unrecognized stages are flagged and not used as arbitrary filesystem paths.

Each attempt records source hashes, text length, reported finish reason,
available token counts/latency, requested output limit from the original
manifest, syntax observations, and structural-schema diagnostics. Missing
metadata remain unknown. A reported zero reasoning-token count does not prove
that the model performed no reasoning: the old client may normalize unavailable
counts, and only its final text—not a full reasoning-channel/API payload—was
persisted by the stage logger.

`finish_reason: length` is reported directly, separately from an end-of-stream
syntax symptom. The latter alone is not proof of truncation by the provider.
Recorded completion-token counts and requested limits are compared without
claiming an actual server cap, missing reasoning content, or a cause that the
archive cannot establish.

## Parsing observations, without creating new submissions

The audit runs the published package's fail-closed YAML extractor on saved
text, then checks a single object against its pinned IR schema. This is a
diagnostic comparison with the archived parser, not proof that every historical
run used an identical extraction version; original harness/prompt versions
are retained where recorded. Schema conformance does not establish catalog,
dataflow, execution, or semantic correctness.

Possible presentation-only candidates are inspected only within complete
YAML/JSON/unlabeled code fences or explicit `===FILE: serviceflow.yaml===`
(`.yml` also accepted) sections. A candidate must already parse as one complete
schema-conformant IR object. Offsets are **Unicode character offsets**, not
byte offsets; exact candidate content hashes are retained without copying
the content into a new submission. All candidates remain visible; two spans
are ambiguous even if they contain the same text. The tool does not choose
one candidate, fill braces/quotes, invent missing fields, repair malformed
YAML, search arbitrary embedded objects, or run code. Inspection limits are
reported instead of silently treating a partial candidate search as complete.

Empty responses, whitespace, no documents, non-object YAML, multiple documents,
schema-invalid objects, parse failures, missing files, and possible complete
presentation candidates remain separate observations. No earlier repair is
selected because it looks better. The audit does not write `serviceflow.yaml`
or compute recovered semantic scores. Any later extraction policy needs a
newly frozen, separately labeled experiment.

## Run

```zsh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit

caffeinate -ims .venv/bin/python -u scripts/audit_v2_saved_responses.py
```

No API token is required. `--dry-run` verifies the parent and inventories file
names/recorded call metadata/hashes, without classifying response bodies or
creating outputs. The runner runs its own synthetic parser/order tests.
The actual response diagnostic run is left for the user.

Outputs in `audit/outputs/package_v2_response_audit__.../`:

- `summary.md`, `grouped_counts.json`: model/method, terminal-cell, and
  attempt-level observations with explicit denominators.
- `responses.csv`: every inspected response attempt and recorded metadata.
- `cells.csv`: one row per selected cell, including unresolved terminal order.
- `response_diagnostics.json`: full located structural findings/candidates,
  without reproducing the saved response text or inventing API payloads.
- `availability_ledger.json`: all 741 original missing-IR cells, selected or not.
- `cells/.../response_audit.json`: immutable per-cell checkpoints.
- `run.json`, `input_sha256.json`, `implementation/`, `verification.txt`:
  exact selection, environment, input/code pins, code/design copies, tests.

The summary separates **attempt counts** from **cell counts**. Multiple repair
calls for a cell are not multiple independent successful submissions. Possible
wrapper candidates are structural observations, not recovered cells or semantic
passes. Missing text is recorded; tool/inspection errors or limits produce
`complete_with_errors`. Changed inputs produce `inputs_changed`.

Resume the same code/design/input condition:

```zsh
caffeinate -ims .venv/bin/python -u scripts/audit_v2_saved_responses.py \
  --resume /absolute/path/to/package_v2_response_audit__YOUR_RUN
```

Completed checkpoint hashes and identities are checked before reuse and final
aggregation. An interrupted unfinished cell gets a new attempt directory.
Original archived files, v1 scores, the paper, GitHub, and DOI remain unchanged.
See [V2_EVALUATION_DESIGN.md](V2_EVALUATION_DESIGN.md) for the distinction between
an engineering goal, an honest new semantic evaluation, and v1 preservation.
