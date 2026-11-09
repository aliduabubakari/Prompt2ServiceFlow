# Protocol 15: one public-schema repair of saved full IR

The cloud Qwen full-IR response from protocol 12 is strict JSON, finishes normally,
and exactly preserves the four supplied bookkeeping fields. It has eight enum
schema errors. The task uses the topology label `fan_in`, absent from the IR
topology enum, and the catalog capability uses `idempotent` while intent policy
requirements use `required`, `preferred`, `not_required`, or `unknown`. These
public vocabulary differences must not be silently equated. The compact
response is malformed JSON and is outside this protocol.

This new post-hoc intervention tests whether ordinary public-schema feedback
can resolve the schema errors. It is not the original M3 score, frozen M4, or a
semantic repair experiment. The same mechanism can describe existing scalar
enum errors in other documents. This bounded implementation deliberately refuses
other schema-error types rather than guessing missing data or changing schema.

## Rules

1. Verify the parent input fingerprints and both completed response inventories.
2. Read only the saved final full-IR content and the same public schema. Require
   strict JSON and the correct public identity before considering repair.
3. Derive the invalid paths and allowed values from the validator. No reference
   IR, expected output, hidden assertion, or replacement table supplies values.
4. Make at most one model call, returning a JSON patch array. Preserve the
   original complete public user context and original assistant candidate. The
   system/output instructions now request a patch. Model, seed, temperature,
   and top-p retain their original settings; the requested output budget is
   1,024 tokens because only a short patch is needed.
5. Accept only `replace` operations at the original invalid scalar enum paths,
   with values allowed by those paths' public enums. Reject duplicate paths,
   extra fields, missing/unknown paths, other operations, and malformed JSON.
   The harness chooses no replacement. Untouched fields remain byte-value
   equivalent as JSON data. Save the model patch and newly derived candidate
   separately from the original evidence. A partial patch may remain invalid.
6. Record schema validity and preservation of public identity. Do not compile,
   execute, repair additional contract errors, or calculate G6-Assert.

Topology and policy edits can change the stated intent; they are not assumed
to preserve semantics merely because the schema accepts them. Contract and
public-input diagnostics are the next stage if this repair succeeds. The known
CRM reference-source ambiguity remains unresolved and must not be fabricated.

## Run

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`:

```sh
.venv/bin/python scripts/run_v2_enum_repair.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_enum_repair.py
```

Set `DEEPINFRA_TOKEN` in the terminal environment. The tests and dry run are
offline. Actual inference occurs only when the user runs the second command.
Use `--resume /absolute/path/to/output-directory` to resume the same attempt.
An ambiguous dispatch is never automatically repeated, and completed failures
are retained. `complete` means the outcome is recorded, not that repair succeeded.
The original v1, saved scores, submitted paper, and earlier audit outputs remain
unchanged. Any eventual v2 result needs its own declared protocol and denominator.
