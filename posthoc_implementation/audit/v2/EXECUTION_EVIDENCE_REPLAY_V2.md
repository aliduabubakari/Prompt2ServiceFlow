# File-backed execution evidence — protocol 38.1

This zero-LLM follow-up addresses the generic-text outputs behind the 1,937
remaining invalid-JSON checks in protocol 37.0. The benchmark's general
file-backed reference adapter (`scripts/reference_runtime.py`) already records
fixture access and upstream evidence. Its source and the earlier predicate
coverage audit establish the historical origin of these telemetry fields.
This new public profile computes such observations from real public files
and model-declared edges; it does not copy reference task bindings, output
values, assertion targets or fixture manifests into the generated runtime.

## Public profile and eligibility

The versioned profile is `execution_evidence_profile.v1.json`. It applies to
artifact outputs with matching public port/data types `status`, `notification`
or `any`, under the controlled mock runtime. An explicit unsupported-mock flag
or non-JSON media declaration prevents application. Existing scalar/array
values are not replaced. Existing object fields are preserved; only absent
observability fields and the reserved `execution_evidence` namespace are added.
Every concrete public schema must permit this extension. Closed, conflicting
and unsupported schemas remain visible and unchanged. No pipeline, model or
private assertion determines eligibility.

The profile emits actual file counts, record counts, file digests and upstream
artifact evidence. CSV counts exclude the header. JSON arrays count their
elements; a JSON object/scalar counts as one document. JSONL counts validated
records. Text formats count nonempty lines. Recognized binary files are counted
as opaque records, with PDF/PNG signatures checked. The root `fixture.json`
wrapper with `inputs` and `input_modalities` is configuration, not a data row;
its contents are not copied into the output. Empty/corrupt input cannot yield
a successful evidence packet.

Only fixture files named in the verified public workspace inventory are
mounted. Their bytes must also match the frozen reviewed fixture tree. Private
or excluded files cannot be counted as observations. The full reviewed
scenario roster and parameters remain in the evaluator, including conditions
whose public view is empty. Such conditions are recorded as rejected input;
the runtime does not manufacture a successful source read.

Upstream evidence follows explicit input bindings and control predecessors.
Each producer writes a receipt naming its actual outputs and their digests.
Consumers verify the producer and digest before counting an artifact. An
unrelated prior workspace file cannot satisfy a missing declared producer.
Repeated identical writes by the same producer represent one physical artifact
in its receipt; they do not create extra upstream artifacts.
Each producer's bytes are retained under `execution_artifacts/<producer>/`.
Multi-producer bindings use these distinct versions instead of whichever file
last overwrote a shared display path. Output-role matching reads the actual
producer version; the original display path is also retained. This is a
representation change in the new profile, not renaming old saved outputs.
Missing, modified or failed predecessors produce unsuccessful observations.
Tasks execute in a stable topological order using both declared control edges
and the producer dependencies implied by artifact bindings. The IR and its
declared edges are unchanged; implied scheduling dependencies are recorded.
Unsupported/cyclic model dataflow is retained as a blocked observation, while
a blocked reference fails the reference gate. Programs write their
observations and receipts before rejecting invalid inputs/dependencies; those
execution errors remain non-passes.
The evaluator independently re-reads each reported public file and recomputes
its digest, size and record count. It checks coverage against the visible
fixture inventory and verifies upstream snapshot digests. Internally consistent
but fabricated counters cannot pass this conformance check.

## Scope and limits

This is a new controlled execution profile, not a lossless rescore of old
output bytes. It observes access to the public input bundle and real
predecessor artifacts. It does not prove that a service performed a domain
transformation, selected the correct external resource, sent a notification
or computed a missing numerical business result. Domain examples/constants
are not adjusted to match a held-out target. Report the resulting rate as
output assertions under this profile, with the earlier 37.0 baseline retained.

The compiler receives only model IR, recognized frozen mock programs and
public contracts/fixtures. The evaluator receives held-out metadata after
compilation and checks the same predicate operators, values and role matching.
Unknown output roles remain non-passes. The original source IR is copied
byte-for-byte. All old freezes, outputs, manuscript and deposited results are
preserved. The generated-code sandbox denies network access.

## Controls and reference stage

Synthetic tests require actual CSV row counts and a genuine upstream receipt.
They reject empty/corrupt input, absent producers, altered producer files,
forged counters and wrong expected counts. Changing a private expected value
cannot change compilation. Other controls protect closed schemas, scalar
outputs, original domain values, the model graph and the public fixture view.

The runner then executes all 110 retained **staged reference compiler**
submissions from the original control study. It uses the same new compiler,
public fixture view and evaluator as the model replay. The reference gate
requires valid profile/evidence conformance, with at least one observed profile
output across the suite. Reference outputs with no applicable profile remain
explicitly unsupported/unchanged, not evidence of profile success. Rejected
input and skipped downstream outputs are recorded. An entire applicable case
with no profile output fails conformance. Unexpected or schema-invalid profile
outputs stop the batch before any model runtime is executed.

Full held-out reference assertion pass rates are reported separately. They do
not gate/select which cases enter the model replay. Passing the profile gate
does not mean all 110 reference pipelines passed every task assertion or public
gate. All original model identities remain in the declared denominator,
including invalid/missing submissions. Reference controls are never pooled
with model results.

## Run

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
caffeinate -ims .venv/bin/python -u scripts/run_v2_execution_evidence_replay_v2.py
```

The command performs source verification and compilation planning, synthetic
checks, the reference stage, and then the saved model replay. No API token or
model is required. Planning can take several minutes. `--dry-run` performs
metadata planning with zero runtime executions.

On interruption:

```sh
caffeinate -ims .venv/bin/python -u scripts/run_v2_execution_evidence_replay_v2.py \
  --resume /absolute/path/to/package_v2_execution_evidence__RUN
```

Source/plan hashes and individual reference/model checkpoints are verified on
resume. Completed cells are skipped. A failed reference gate leaves a sealed,
resumable diagnostic report. Do not bypass the gate or replace failed cases.
