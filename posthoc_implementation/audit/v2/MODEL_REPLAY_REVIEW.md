# V2 targeted replay: review and next decision

Reviewed on 2026-10-24.

Run: `../outputs/package_v2_model_replay__20261024T170924Z__018604e1/`.
Package: `2.0.0-candidate.1`; diagnostic protocol: `4.1.0`.

## 1. Completion and integrity

All 221 fixed targets were recorded, with no runner-error records and zero
LLM calls. The verification log records 36 passing v2/control/replay tests.
The run reports unchanged input hashes. Review independently rechecked all
43,356 recorded input-hash entries against the current files; they match.
All records report that the original bindings were not changed.

The original 2,970-cell M3–M5 ledger remains present: 2,211 compositions were
inventoried, 741 lacked final saved IR, and 18 had invalid saved IR under the
earlier diagnostic parser. The 15,379 out-of-scope service/version occurrences
remain coverage information rather than disappearing from the design.

## 2. What the path correction changed

| Original v3 state | New v2 state | Invocations |
|---|---|---:|
| Executed | Executed | 12 |
| Execution error | Executed | 8 |
| Execution error | Execution error | 3 |
| Unsupported operation | Unsupported operation | 167 |
| Invalid binding or unsupported input mapping | Same category | 31 |
| Total | | 221 |

Five recovered invocations previously hit a dataset/metadata filename
collision. Three previously used absolute logical output paths outside the
v3 adapter's supported prefix. The v2 namespace convention handles these
without overwriting another output port or writing to those host paths.

The eight recoveries are four DeepSeek M5 and four SINTEF M5 invocations.
They demonstrate a correction to the diagnostic v3 execution interface with
saved bindings held fixed. They are not eight new semantic passes in the
submitted experiment: the diagnostic executor, output layout, and measurement
scope differ from the published whole-pipeline evaluation.

## 3. Successful execution and changed inputs

| Model / method | Successful invocations | Changed-input checks passed |
|---|---:|---:|
| Qwen-480B M5 | 3 | 3 |
| DeepSeek-Flash M5 | 10 | 10 |
| SINTEF M5 | 7 | 7 |
| Total | 20 | 20 |

All 20 passed public output schemas, complete output-path checks, and the
limited changed-input probes. All are CSV loader invocations, distributed
across 14 model cells and four distinct pipelines:

- `main/executive_sales_dashboard`.
- `main/file_arrival_watcher`.
- `main/supply_chain_shipment_etl`.
- `validation/val_csv_to_warehouse_daily`.

The counts include repeated cells and multiple vendor invocations within one
pipeline, so they are not 20 independent pipeline successes. No saved-model
retention or JSON-to-CSV invocation reached successful execution in this
study. The retention adapter has reference-control evidence; the exporter
still has synthetic verification rather than a successful saved-model replay.

This supports actual input use for the executed CSV operations, not correct
service selection, semantic correctness of every output field, branch
behavior, or completion of the surrounding workflows. Do not infer that M5
outperforms M3/M4 from this coverage-limited result.

## 4. Remaining execution errors are explicit configuration mismatches

The three remaining execution errors are DeepSeek M5, sample index 2, in
`main/supply_chain_shipment_etl`, one for each vendor input. Each invocation
requires an `origin` column absent from its supplied CSV header:

```text
shipment_id,sku,quantity,ship_date,destination
```

They still fail with `CSV is missing required columns`. The new executor does
not invent the column, drop the requirement, or alter the saved parameter.
This is a concrete binding/configuration-to-data mismatch. Whether the source
requirement itself is fully specified is a separate question.

## 5. Most selected invocations still cannot be executed

The 167 unsupported outcomes break down as follows:

| Limitation | Invocations |
|---|---:|
| Requires an upstream-produced result | 99 |
| No explicit external fixture reference | 64 |
| No explicit logical reference time | 3 |
| Typed CSV `expected_schema` rules not implemented | 1 |

The last condition appears in the raw record's `execution_errors` rather than
its `reason` field; its meaning was checked directly, not treated as unknown.

The 31 invalid-binding/input-mapping outcomes comprise:

| Recorded reason | Invocations |
|---|---:|
| Input fixture reference form outside supported convention | 19 |
| Required output ports missing or duplicated | 9 |
| Required input ports not bound | 3 |

The input-mapping category is mixed: unsupported path forms are not
automatically unsafe paths, and missing fixture links are not automatically
failures to follow an original instruction. The earlier audit found that
fixture previews were omitted from M3/M4 initial prompts and `fixture_ref`
was optional in the public artifact schema. Those original exposure and
execution-contract gaps cannot be removed by replaying unchanged outputs.

All selected M3/M4 invocations remain blocked or rejected at these interfaces.
No amount of additional replay under the same unchanged scope supplies
missing input mappings or implements absent producer operations.

## 6. Next decision

The narrow path correction is validated on reference and saved-model
invocations. Do not run another large isolated-service replay just to obtain
the same coverage pattern, and do not launch a full paid rerun yet.

The next useful v2 milestone is a complete, declared workflow family:

1. Define the public executable-input interface, including fixtures and logical
   time, and render it into the actual prompts for any new generation condition.
   Test the rendered prompts, not only a Python view. This is a separately
   labeled generation condition; it does not fix already-saved bindings.
2. Implement producer-to-consumer artifact execution for the selected reusable
   family, with explicit conditional behavior where required. Unsupported
   operations must remain unsupported rather than silently mocked.
3. Require complete reference-workflow controls and operation-specific
   negative/changed-input tests before evaluating model workflow success.
4. Then replay saved compositions where the required explicit bindings exist.
   If new generation is needed for absent public links, begin with a small
   fixed M3/M4/M5 comparison under the new v2 input interface, not all 110
   pipelines. Preserve the old results and separate any binding-repair
   condition from unchanged-composition replay.

The objective is not to obtain higher scores by relaxing tests. It is to
establish a valid executable path from public inputs through actual service
operations to meaningful semantic checks. This run closes a path-handling
problem; it does not yet close that full path.

Only this review document was added. The run, v1 package, DOI, paper, original
model outputs, source code, and prior candidate implementations were not
modified during review.
