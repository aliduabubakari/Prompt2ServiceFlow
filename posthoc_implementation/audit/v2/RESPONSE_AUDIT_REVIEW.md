# Review of saved-response availability and format failures

Reviewed 25 October 2026. Evidence:
`audit/outputs/package_v2_response_audit__20261025T112243Z__17b563f4/`.
Protocol 11.0.0 completed without inspection errors or unresolved call order.
The review reverified 50,384 input/code fingerprint entries and all 471 cell
checkpoint hashes. No response, parser, method, score, or published artifact
is changed here.

## Main result

Every one of the **891 recorded calls** in this selected failure cohort has
`finish_reason: length`. No complete schema-conformant IR was found in the
saved text using the audited complete-fence/file-marker extraction rules.
There is no demonstrated parser-only recovery in this cohort.

The cohort is all 471 original missing-IR cells whose recorded status is
`parse_error`: 331 M3 cells and 140 M4 cells. M4 contributes an initial call
and three repair calls per selected cell. These observations must not be
generalized to all calls in the full experiment or to the providers outside
the recorded configurations.

| Terminal saved-text state | Selected cells |
|---|---:|
| Empty content | 183 |
| End-of-stream parse error | 190 |
| Other parse error | 98 |
| Total | 471 |

At attempt level, 295 files are empty, 378 have end-of-stream parse errors,
and 218 have other parse errors. The first two tables have different
denominators: 891 attempts are not 891 independent pipeline submissions.
All empty files are in the selected SINTEF cohort. No response file was
missing and no attempt order needed to be guessed.

The summary's 295 `not_inspected` presentation observations refer to empty
text for which no wrapper search applies, not 295 unprocessed calls. The
remaining 596 attempts were searched and had no complete explicit candidate.
End-of-stream errors alone would not prove provider truncation; here the
separate recorded finish reason is `length` for all calls, including those
with other syntax errors or no visible content.

## Recorded token limits and usage

| Model | Selected cells | Calls | Configured/requested limit recorded in manifest | Completion tokens recorded per call |
|---|---:|---:|---:|---:|
| DeepSeek-Flash | 6 | 15 | 16,384 | 16,384 |
| Qwen-480B | 7 | 16 | 16,384 | 16,384 |
| SINTEF Qwen | 458 | 860 | 16,384 | 8,192 |

For SINTEF, every selected call reports 8,192 completion tokens despite the
manifest's 16,384 setting. This warrants checking the actual request/server
output configuration; it does not establish which component enforced a cap.
The complete historical request/response payloads were not retained by the
stage logger, so the manifest alone cannot prove every transmitted setting.

The cohort records 22,531,526 prompt tokens and 7,553,024 completion tokens
(30,084,550 total). Completion counts need not equal visible final-answer
text: the empty files also record token consumption. All recorded reasoning
counts are zero, but the client can normalize unavailable counts and only
persists `choice.message.content` as stage text. The archive therefore does
not establish whether reasoning consumed the budget, whether content was
omitted elsewhere, or another reason the final text is empty. Do not claim
a particular reasoning-channel/provider failure without new evidence.

## Consequences for the root-cause analysis

The 471 parse-error missing-IR outcomes are associated with reported output
length stops. They are not evidence that a complete proposed composition
was executed and failed its numerical assertions. Repeating whole-document
parse repairs under the same insufficient output allowance did not produce
a complete IR in these selected M4 cells.

This is a distinct layer from the census's catalog, writer, fixture, and
runtime-definition issues. Fixing generation availability will not itself
make a generated workflow semantically correct. Likewise, implementing a
correct service kernel cannot recover a final composition that was never
saved. Original end-to-end results still measure the recorded configuration;
they should not be read simply as conditional semantic accuracy of complete
model outputs.

Empty files contain no final IR to extract. Incomplete fragments may contain
some useful decisions, but filling missing text or using public metadata to
construct a new document would be a new reconstruction/repair method. It is
not faithful presentation normalization, and no such repair is performed or
credited by this audit. No earlier attempt is substituted for the terminal
one. A broader hypothetical reconstruction method is not ruled out; it would
need its own frozen rules and evaluation.

## Recommended next step: v2 generation and runtime foundations

There is enough evidence to stop pursuing a parser-only rescue of this cohort.
Prepare generic v2 corrections before another paid full-corpus run:

1. **Record and classify generation outcomes explicitly.** Preserve assistant
   content, available reasoning/tool fields, token metadata, finish reason,
   configured limits, and available actual request settings without API
   credentials. Keep reasoning distinct from the submitted final IR. Detect
   empty/length-stopped output before treating it as an ordinary syntax-only
   error. Output-budget exhaustion remains an operational non-pass in a
   declared end-to-end denominator, not a convenient exclusion from scores.
2. **Reduce repeated response content by design.** Use a versioned compact
   output/transport format and deterministic expansion of verified public
   bookkeeping fields (for example source/catalog hashes). Model-authored
   service choices, task decomposition, parameters, fixture decisions, and
   wiring must remain model decisions. Do not copy reference graphs/bindings,
   invent semantic fields, or silently apply a new format to v1 scores. This
   is a changed v2 method/harness condition, not just a looser parser.
3. **Verify supported output capacity with a bounded future pilot.** Compare
   recorded configuration, actual request metadata, finish flags, and complete
   responses before scaling. Match and report decoding/repair budgets. Do not
   merely assume that a larger context window provides a larger completion
   allowance or that changing a number in a config changes server behavior.
   A live probe/generation experiment has cost and is a later user-run step.
4. **Keep data/runtime corrections separate.** Resolve or document the
   preselected fusion family's missing/unclear third-source roles and public
   numerical/output semantics, and review the ten reference/descriptor
   parameter inconsistencies. Require reference/value/negative controls
   before judging new generated workflows. Generation/interface improvements
   alone do not solve these benchmark/runtime limitations.

Evaluate a small, clearly scoped v2 study with frozen rules and independent
new input checks before wider generation. Report execution coverage, original
and new outcomes, repair effects, and success on the full declared task set;
do not chase a 50% threshold or advertise a conditional pass rate as full
coverage. Preserve v1's tag/archive/DOI and publish v2 separately if validated.
See `V2_EVALUATION_DESIGN.md` for the agreed evidence and reproducibility rules.
