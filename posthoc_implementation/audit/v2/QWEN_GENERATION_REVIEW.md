# Review of the Qwen full/compact generation pair

Source: `audit/outputs/package_v2_generation_pilot__20261025T171135Z__3413ad6d`.
Verified all 50,864 input fingerprints, the unchanged-input run flag, and both
completed request/response/result inventories. No saved result was replaced.

| Condition | Final response | Completion tokens | Outcome |
|---|---|---:|---|
| Full IR | strict JSON, normal stop | 2,862 | Eight schema enum errors |
| Compact IR | malformed JSON, normal stop | 1,823 | Parsing failed before decoding |

The full response exactly preserves all four verified bookkeeping fields. Its
summary's false identity flag is not evidence of a wrong identity: the original
classifier exits at schema validation. An independent comparison confirms the
identity values. Its schema errors comprise one topology value `fan_in` and
seven intent-policy values `idempotent`. No other full-schema violations were
reported by the validator. This does not establish contract closure, correct
service decisions, correct fixture binding, or semantic correctness.

## Public vocabulary evidence

The task itself contains `Topology pattern: fan_in`, whereas the IR enum lists
`linear`, `branch_merge`, `fan_out`, `fan_out_fan_in`, `sensor_gated`,
`staged_etl`, `mixed`, and `unknown`. The catalog uses `idempotency: idempotent`
as a capability property, while the IR's intent-policy requirement uses
`required`, `preferred`, `not_required`, or `unknown`.

These are observable public-interface vocabulary differences. They require
interpretation rather than literal copying. A capability's idempotency and an
intent's idempotency requirement are distinct statements, so substituting one
for the other is not an established semantics-preserving normalization.
Likewise, do not silently map every task topology label to a preferred enum.
The observed copying is one plausible source of these schema failures, not
proof that all semantic failures originate in the data or prompts.

## Compact format

The compact response mixes positional array entries with keyed object fields.
For example, a keyed `schedule` member appears inside an array. The first JSON
parser error is at zero-based character 232. Codec decoding is never reached.
Together with the malformed SINTEF compact response, this is sufficient reason
to stop pursuing positional compaction as the next development step. It is not
a general performance ranking or a proof that other compact representations
cannot work.

## Next intervention

Protocol 15 tests one model-authored, public-schema-guided patch to the saved
full response. Paths and permitted values are derived from the schema errors.
The harness accepts changes only at those existing invalid enum fields; it
does not pick replacements, amend service/fixture choices, or change the schema.
The patch is saved separately and its schema outcome is reported separately.
It is explicitly a post-hoc intervention, not an original M3/M4 result.

Offline preparation passed 44 tests and the frozen-parent dry run. There is at
most one new API request, no automatic retries, and a requested output budget
of 1,024 tokens for the short patch. No live inference occurred in this review.
See `ENUM_REPAIR.md` for the design and user-run command.

If the patch succeeds, inspect contracts, inputs, and runtime applicability next.
The known CRM third-source specification issue remains unresolved. Schema
success cannot justify executing a fabricated input or claiming G6-Assert
success. Preserve all denominators and previously recorded failures when
reporting any later v2 experiment. Original v1 and the submitted paper remain
unchanged.
