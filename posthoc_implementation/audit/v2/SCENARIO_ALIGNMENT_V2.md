# Evaluator-only scenario alignment audit — protocol 34.1

This read-only audit follows the completed protocol-33 CSV replay. It freezes
all 37 primary M3–M5 cells that the earlier 2,970-cell attribution classified
as recorded assertion scenario-alignment failures. These are eight Main tasks,
selected for diagnosis of a recorded error category, not a new performance
sample. The configuration contains every identity; none may be dropped.

Version 34.1 handles ordinary YAML aliases present in original runtime metadata.
The initial 34.0 candidate and its freeze remain intact; metadata preflight
caught its overly strict alias refusal before the user-run audit. The new
reader uses safe YAML constructors and rejects cycles, executable tags,
non-JSON values, depth above 80 and more than 100,000 expanded nodes. The
2 MiB file limit remains. This affects metadata reading only; no program runs.

## Questions

1. What scenario executions did the corrected publication report record?
2. What input parameters and fixture roots did the saved submission declare?
3. Do current public fixture bytes match the public manifest hash recorded in
   that original run and every file hash inside that manifest?
4. Could a reviewed scenario be associated unambiguously with a recorded run
   using identical parameter maps and the complete fixture-tree hashes?
5. How much required scenario coverage is absent or unresolved, and are any
   expected outputs retained at the inspected submission paths?

## Strict associations and coverage

Labels, list order, a single matching CSV, common basenames, empty missing
directories and favorable outputs are not grounds for an association. Do not
drop fixture.json or other extra files to make two roots look identical.
Parameters compare exact JSON values, including boolean versus integer types.
Missing parameters are not supplied from private scenario definitions.

A verified exact name/context association is retained. A differently named
context is associated only when full input contexts match uniquely in both
directions after exact matches. This is diagnostic input provenance, not a
new alias applied to the scorer and not evidence of semantic correctness.
Duplicate execution/declaration IDs are inspection errors.

The runtime fixture-root convention is recorded faithfully: use an explicit
root, otherwise the named fixtures/scenarios directory when present, otherwise
fixtures/inputs. No model-generated program is interpreted to infer inputs.
Task parameters may not actually have been used by a generated script; matching
declared input contexts does not certify that program's business behavior.

Reviewed scenarios without a supported association remain unresolved. A
cardinality lower bound reports at least how many additional labeled executions
are required when there are fewer recorded runs than reviewed scenarios. It
does not decide which unmatched scenario an unknown nominal run represents.
One positive execution can never count as both positive and negative coverage.

## Retained outputs and score boundaries

The original scorer consumed temporary execution snapshots without retaining
them in score.json. This phase inventories actual files at reviewed relative
output paths inside the original submission. A present loose file is not a
trusted, scenario-associated snapshot. A missing retained file does not prove
that the temporary original execution failed to produce it. Static generated
writer code is not used to reconstruct output bytes.

No retained-snapshot format is accepted for rescoring by this condition. No
assertion predicate, scorer, generated script, workflow, compiler or backend is
run. No semantic score is computed or replaced, even if a supported input
association is found. The corrected publication ledger remains authoritative;
older raw manifest pass flags are recorded for comparison, not reused as a
replacement paper baseline.

## Provenance, outputs and privacy

Verify the protocol-33 input manifest and sealed output evidence, the original
attribution checkpoints, exact 37-cell roster and corrected publication records.
Pin original workspace manifests and their listed public files, saved IR,
runtime metadata/scripts, reviewed fixture trees and assertion metadata. Absent
expected output files are pinned as MISSING. Directory inventories are checked
again at completion to detect added files. Each cell gets a hashed result and
the entire output folder gets an end-of-invocation seal.

The implementation/configuration/tests/documentation have a separate versioned
freeze lock. Existing scripts, results, v1 archives and the paper are untouched.
Inspection errors retain their identities and produce a nonzero exit with a
complete_with_inspection_errors report instead of silently removing cells.

Detailed reports contain evaluator-only scenario parameters and assertion paths.
They are saved under audit/evaluator_only and must never be copied into public
generation workspaces or prompts. No model/server/API token or Docker is needed.

## Run

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/audit_v2_scenario_alignment_v2.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_scenario_alignment_v2.py
```

The dry run checks the frozen selection and input inventories only. The actual
command first runs synthetic provenance tests and then inspects every selected
cell, writing summary.md, aggregate.json, frozen_roster.json, per-cell reports,
input/output hashes and verification.txt. There are no runtime or inference
requests and no new score. An interrupted run stays intact; rerunning creates
a fresh folder. This small offline audit does not require resume controls.

After reviewing it, decide whether the evidence supports a separately labeled
evaluation with preserved IR and correctly provisioned scenario inputs, or a
new generation study using a corrected public contract. Missing executions
and unimplemented business services cannot be fixed by renaming score labels.
