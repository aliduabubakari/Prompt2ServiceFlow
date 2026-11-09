# Offline cross-task implementation and public-input coverage

This phase plans the next multi-task semantic study without making LLM calls,
running reference/model workflows, repairing saved code or changing scores.
It follows the completed two-model, three-seed relational development study.
All previous methods, manifests, data, paper artifacts and results stay intact.

## What the audit checks

All 110 original task identities and Main-40/Validation-20/Extension-50 labels
are retained. Selection is based only on reference service/version requirements,
public source files and explicit task-scope reviews. Model success, availability
and token costs do not enter task ranking. Reference IR supplies a structural
service roster, not replacement model bindings, business outputs or runtime.
No private assertion or reference program is executed or used to infer rules.

Implemented service names are read from the existing trusted registry source
using AST inspection, without executing registry values. The six-operation
window and seven-operation relational backends require exact versioned rosters.
The local CSV mechanism and isolated port helpers are listed separately:
kernel availability does not establish an actual M3/M4/M5 IR execution route.
No services are borrowed across backends without a verified composition route.
An extra alignment/forecast/branch step cannot be discarded to make a task fit.

The public builder inventory is checksum-verified. Named nominal manifest
sources are checked for presence, contained paths, parseable record/object
structure and CSV headers, within a bounded inspection size. A remote source
is not fetched. When no input-role manifest exists, real public files are
reported as unmapped rather than automatically called missing. Existing
explicit profiles alone authorize field/role-presence checks; new mappings
are not guessed from similar names. Structural presence is not numerical
correctness, full input validation or complete task-intent coverage.

The two already studied development tasks retain their scope disclosures:
building-energy public task wording differs from the declared window profile;
support-profile routing uses the supplied policy and does not implement missing
plan lookup/freshness. Successful controls do not erase those differences.
Both are excluded from the new-task review queue. New tasks still require an
explicit semantic review and reference controls before generation.

`new_generation_ready` is deliberately false for every task in this static
report. That is a limit of this planning phase, not a claim that every task is
impossible to execute. A complete service roster is an upper bound, not a
semantic-success score. M0-M2 need a separate equivalent direct-Argo business
execution route; this audit does not quietly convert their outputs into IR.

## Provenance and outputs

The command checks the completed DeepSeek/Qwen evidence and original method
freeze, then verifies the 110-task census and current reference/public sources.
New planning code and policy are separately pinned. Only these new planning
entry points are excluded from the old dynamic method inventory and pinned
in the new run instead; no frozen method/tool/data file is excluded. The
initial and final input hashes must match. Each completed task row has its own
checkpoint hash, and resume refuses changed sources, policy or implementation.

Output files:

- `summary.md`: counts, complete backend rosters and the review queue.
- `coverage.json` / `coverage.csv`: all 110 task records, including input and
  service gaps, stratum labels, explicit profile checks and scope notes.
- `review_queue.json`: deterministic new-task public-contract/implementation
  review order, not an execution-ready selection or ranking by model failures.
- `implementation_backlog.json`: missing registered services and affected tasks.
- `run.json`, `input_sha256.json`, per-case checkpoints and `verification.txt`:
  reproducibility and integrity evidence.

Inspection errors remain visible and produce `complete_with_errors`; ordinary
unsupported operations or incomplete input contracts are coverage findings,
not tool errors or model failures. Do not stage evaluator planning records,
reference bindings or future private controls in model workspaces.

## CLI

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/audit_v2_cross_task_coverage.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/audit_v2_cross_task_coverage.py
```

No API key, model server or Docker daemon is needed. The command executes only
the audit's synthetic unit tests, never a task workflow. It prints a row for
each inspected task and the final `summary.md` path. On interruption:

```sh
caffeinate -ims .venv/bin/python -u scripts/audit_v2_cross_task_coverage.py \
  --resume /absolute/path/to/the/coverage/output-directory
```

After reviewing the report, choose tasks by public completeness and operation
coverage, resolve shared implementation/contract gaps, run reference/numerical/
rejection/mutant controls, then freeze the multi-task generation design before
spending on new inference. No profile is inferred from hidden expected answers.
