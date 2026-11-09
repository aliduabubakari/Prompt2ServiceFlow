# Original-corpus coverage planner: review

Reviewed on 2026-10-24.
Run: `../outputs/package_v2_coverage__20261024T210210Z__2c723644/`.

## Completion and the single reported error

The scan retained all 110 original reference workflows and all 5,940 model
cells. All 110 reference analyses completed. There were zero LLM calls and
zero saved-code/workflow executions. Input fingerprints were reverified and
are unchanged. The verification log records 18 passing planner tests.

`complete_with_errors` is caused by exactly one model cell:

```text
deepinfra-deepseek-v4-1-flash/m5/extension/satellite_change_report_assembler/2
```

Its saved final IR uses `from_` instead of `from` on all six control-flow
edges. The public schema requires `from` and rejects additional `from_`
properties. An independent schema check confirmed 12 edge-schema errors:
six missing required fields and six unexpected properties.

The planner then indexed `edge['from']` and produced a caught `KeyError`.
Thus there are two distinct facts: the saved artifact has a malformed edge
representation, and the planner should classify it cleanly rather than call
it an unexpected inspection error. No model artifact or edge was corrected.

The affected cell's control-flow analysis and missing-service aggregation are
incomplete. Other recorded cells and all reference-side rankings remain
available. Repeating the entire unchanged scan would reproduce the same
outcome; it is not necessary to continue planning. A subsequent scanner version
should preserve malformed edges as explicit diagnostic observations. Renaming
`from_` in the model output would be a separate repair intervention, not a
planner robustness fix.

## Coverage retained

| Route/outcome | Cells |
|---|---:|
| Direct Argo artifact inventoried | 2,721 |
| Direct Argo parse/shape error | 243 |
| Direct Argo artifact absent | 6 |
| IR analyzed | 2,210 |
| IR inspection error described above | 1 |
| IR invalid document/structure | 2 |
| IR YAML parse/scanning error | 16 |
| IR final artifact absent | 741 |
| Total | 5,940 |

No original IR model composition has a complete service roster supported by
the candidate.2 workflow executor. Static analysis still certifies no original
cell as execution-ready. These are coverage findings, not semantic scores.

## Do not automatically adopt the proposed three-pipeline cohort

The tentative shared-implementation proposal is:

- `main/multilingual_product_review_analysis_v1`.
- `main/procurement_supplier_validation_v1`.
- `main/medical_facility_accessibility_v1`.

The first pipeline has no flagged network/credential requirement or missing
explicit public fixture link, but still needs language detection, sentiment
scoring, feature extraction, and formatting. Its public sentiment contract
requires a configured model and states that acquiring model weights is outside
the catalog contract. Network-free does not mean model-free, precisely
specified, or trivial to implement. Do not substitute labels or keyword rules
selected to match private expected results.

The second introduces Wikidata entity reconciliation with a required network
policy. A fixture-backed resource label does not itself provide a verified
offline entity index or faithful reconciliation computation.

The third introduces geocoding, credentials/network dependencies, and two
unavailable public GeoJSON inputs. It is not a ready-to-run zero-inference
cohort. The greedy proposal favored shared formatting code; that is a workload
hint, not a sound substitute for reviewing the entire execution interface.

The one-service alternatives also need care: Airflow log cleanup has deletion
semantics, while Snowflake, GraphQL, and email-related operations need real
resource/backend review. Do not act on original absolute cleanup targets on
the host or substitute another database and claim the original backend passed.

## More suitable next candidate for explicit specification review

A deterministic bounded-window family is a better candidate to assess next
than automatically adopting the above three-pipeline mix. For example,
`extension/building_energy_window_aggregation` has:

- Six missing exact service implementations.
- No input/control/schema issues flagged by the static scan.
- No required network/credential or deletion flags.
- Actual public energy-reading JSONL and building-registry CSV fixtures,
  with explicit active-scenario fixture links and window parameters.

These properties make it a candidate, not an execution-readiness certificate.
Its descriptors are broad operation-profile contracts. The public task mentions
hourly/daily windows, while the active fixture specifies a 30-minute window.
Grouping, deduplication, boundary inclusion, energy aggregation, demand metrics,
and publication semantics must be reviewed and made explicit before claiming
a faithful implementation. Ambiguity must not be resolved by looking up the
private expected answer.

`extension/clickstream_session_window_batch` and
`extension/notification_delivery_checkpoint_audit` are additional deterministic
local candidates with shared conceptual sort/window operations. They have
different exact service IDs/contracts; they must not be treated as aliases
without review. The known clickstream checkpoint-file exclusion also needs its
previously reviewed public/private-field correction kept as a separate input
intervention, not silently mixed into unchanged replay.

## Recommended next step

1. Preserve this completed report. Do not rerun all 5,940 cells just to remove
   the single status error. Record the malformed artifact and add a tolerant
   scanner guard in a separately versioned diagnostic update when needed.
2. Review and freeze an explicit public execution specification for one original
   bounded-window workflow, resolving source/fixture ambiguities transparently.
3. Implement shared, parameterized ingestion, validation, deduplication,
   windowing, aggregation, and publication operations. Avoid switches that
   hardcode a particular pipeline's expected outputs.
4. Run that original workflow's reference/runtime controls plus independent
   negative and changed-input checks. Do not replace its task with the earlier
   CSV round-trip control.
5. Replay its saved model compositions without new generation where bindings
   are explicit and supported. Retain malformed, missing, and unsupported cells.
   Public-input corrections, deterministic binding repair, and executor-only
   replay must remain distinguishable conditions.

No additional experiment, code correction, API call, or publication action
was launched during this review. V1, the DOI, paper, original artifacts, and
the protocol 6.0.0 report remain unchanged.
