# Protocol 17: bounded public-contract graph/input repair

Protocol 16 found that fixing eight schema enums left ten checked contract and
dataflow findings unchanged, with no explicit artifact fixture links. This
pilot uses public contracts to request one new patch from the same model. It
is an exploratory intervention on one saved candidate, not original M4/M5,
a method comparison, a runtime implementation, or a semantic result.

The model receives the original full public task/catalog/schema/fixture context,
the schema-repaired candidate, the offline static findings, and
`PUBLIC_ARTIFACT_INPUT_CONTRACT.md`. The latter states general output-binding,
artifact-writer, and public-input requirements. It also states what is unknown:
no merge implementation is registered here and generic operation labels do
not supply executable transformation semantics. The public rules contain no
pipeline-specific replacements and no hidden expected outputs.

The response is an object with `patch` and `unresolved_requirements`. Accept
only unique `replace` operations at these derived paths: `/artifacts`,
`/control_flow`, each existing intent's `inputs`/`outputs`, and each existing
binding's `input_bindings`/`output_bindings`. Those paths do not overlap.
The model authors the complete replacements. No harness rule creates artifacts,
chooses fixture files, splits graph stages, or supplies a missing source.
The patch cannot alter intent/service identities or order, service versions,
parameters, task, public identity, policies, runtime, or validation expectations.

Existing service/profile decisions are deliberately held fixed to isolate the
binding/graph intervention; a later public operation/runtime specification may
still require a separate change. Missing or ambiguous source data must remain
unresolved. An empty model-declared unresolved list is not independent evidence
that all inputs are sufficient. In particular, the previously documented CRM
reference-source ambiguity must still be reviewed.

After a patch, validate the complete original IR schema. For schema-conformant
candidates, rerun the same public static checker and input/writer context review.
Retain detailed remaining defects, unresolved file links, multiple writers,
model-declared uncertainties, and the raw response/patch. Literal type rules,
catalog defects, runtime signals, and input review cues remain distinguishable.
Do not execute code or derive semantic success from zero static findings.

One sequential inference call maximum, no automatic retries, requested output
budget 4,096 tokens for the patch. Other model settings retain their original
values. Resume never repeats an ambiguous dispatch or completed failed result.
Inputs, public files, completed parents, and response files are fingerprinted.
The extra public contract makes this a new labeled v2 condition; do not pool
it silently with original results. v1 and the submitted paper stay unchanged.

## User-run command

From `/Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit`, with
`DEEPINFRA_TOKEN` exported:

```sh
.venv/bin/python scripts/run_v2_contract_repair.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_contract_repair.py
```

Only the second command makes the model call. To resume the same attempt, add
`--resume /absolute/path/to/the/output/directory`. Review the summary and detailed
candidate before another call, runtime work, or broader experiment.
