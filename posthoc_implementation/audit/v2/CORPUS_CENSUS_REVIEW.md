# Review of the completed corpus-wide static census

Reviewed 25 October 2026. Evidence:
`audit/outputs/package_v2_corpus_census__20261025T101943Z__f7745ed7/`.
Protocol 10.0.0 completed with zero inspection errors and unchanged inputs.
This review reverified all 49,374 input/code fingerprint entries and all 110
per-case checkpoint hashes. No generation, repair, execution, or publication
change is made here.

## Complete accounting, without turning static findings into semantic scores

The census retains 5,940 original cells from 110 pipelines. Direct-Argo M0–M2
and IR M3–M5 remain separate routes, 2,970 cells each.

| IR availability/inspection outcome | Cells |
|---|---:|
| Missing saved IR at the exact inventoried final location | 741 |
| Saved file with YAML parse error | 16 |
| Saved non-object document | 1 |
| Inspected object with checked hard findings | 1,288 |
| Inspected object without those checked hard findings | 924 |
| Total | 2,970 |

The last group is not certified executable or semantically correct: it can
still have literal type-rule, input, runtime, or semantic-definition review
needs. `inspected` means processed, not valid. The standalone aggregate count
of 1,289 cells with hard findings includes the one non-object document.

For direct Argo, 2,721 files were inventoried, 243 had parse/shape problems,
and six were missing. This is resource/YAML availability, not Argo validation
or task execution and not comparable new full-pass scores.

IR category counts overlap:

| Finding/review category | Cells affected |
|---|---:|
| Structure | 196 |
| Checked public contract | 1,141 |
| Dataflow | 476 |
| Literal frozen type-equality rule | 684 |
| Input context | 1,175 |
| Execution context | 1,706 |
| Public runtime-semantic review signals | 1,830 |

Do not add these counts or interpret them as disjoint causal contributions
to low G6-Assert. In particular, opaque object parameters and unenumerated
profiles are descriptive review signals, not automatic contract errors.
Network/credential requirements and missing optional fixture links may have
legitimate runtime meanings that static inspection cannot resolve.

## Output availability is a substantial separate issue

Among the 741 missing IR files, the original recorded method statuses are:

| Original recorded status | Missing IR cells |
|---|---:|
| `parse_error` | 471 |
| `agent_step_budget_exhausted` | 237 |
| `llm_error` | 2 |
| No recorded method status in the fixed source ledger | 31 |

No missing file is automatically attributed to model reasoning. SINTEF M3
has only 6/330 saved IR files; its other 324 cells have recorded parse-error
status. SINTEF M4 has 134 missing parse-error cells. Qwen M5 has 161 missing
budget-exhausted cells. Availability and generation/agent behavior therefore
need their own account before any claim about semantic reasoning ability.

Two illustrative spot checks (not a representative sample) used the first
missing SINTEF M3/M4 cells in the fixed ledger, both for
`extension/access_entitlement_recertification`, sample 0:

- The saved M3 `responses/m3_ir.txt` contains **zero characters**; the method
  error says no YAML documents were found.
- M4's final `responses/m4_repair_parse_3.txt` ends inside an unterminated
  quoted field. Its recorded error is an unexpected end of stream.

These examples do not establish that all parse errors have the same cause.
An empty or truncated saved response cannot be reconstructed as a faithful
submission by simply relaxing a parser. A response-level census should first
distinguish empty, truncated, wrapper-only, structurally invalid, and
unavailable responses. Do not invent missing text or select a successful
intermediate attempt after looking at scores.

## Explicit closure improves while runtime/data interpretation remains

For the two cloud models, checked contract findings are less frequent in M4
than M3 among the inspected IR files:

| Model | M3 files with contract findings / inspected | M4 files with contract findings / inspected |
|---|---:|---:|
| DeepSeek-Flash | 257/327 | 33/327 |
| Qwen-480B | 278/325 | 86/326 |

These are descriptive static counts, not significance tests or semantic
rankings. M4 still has input-context findings in 183 DeepSeek cells and 189
Qwen cells. The SINTEF M3/M4 comparison has severe availability differences
and should not be presented as the same comparison on complete usable outputs.

Across IR cells, 706 have at least one required unbound port and 356 have
intent/binding artifact-set disagreements. There are 5,373 required-port
finding occurrences, of which 3,199 concern `execution_report`, affecting
364 cells. Status completion may improve observability/closure but the paired
study already showed that it rarely restores missing computation inputs.

There are also 5,765 literal artifact/port type mismatches affecting 684
cells; many compare declared `any` with a more specific type such as JSON or
table. These reproduce the old validator's literal type rule. They are not
proof that these pairs are inherently incapable of correct computation.

## Benchmark/reference contract mismatches need their own review

All 110 reference IRs were processed without structure/dataflow/literal-type
findings, but ten have 16 explicit parameter type/enum mismatches under the
additional descriptor checks. Examples verified against public descriptors:

- `main/content_moderation_pipeline`: reference `publication_mode: standard`,
  while the descriptor permits only `artifact_only` or `platform_publish`.
- `main/assignment_solution`: two `sql_statements` values are the string
  `SELECT 1`, while the descriptor declares an array.
- `main/database_partition_check_etl`: reference `success_condition:
  row_count > 0`, while the descriptor enumerates `row_exists`,
  `row_count_equals`, or `scalar_true`.

These are concrete reference/descriptor inconsistencies, not model-generated
errors. The original closure validator does not check all these parameter
value constraints, so this is not a claim that its original recorded gate
results have changed. Decide whether the source requirement calls for a
different descriptor or a different reference value before making a separately
versioned v2 correction; do not simply make gold pass the new checker.

Reference findings also include input-context review in 31 pipelines and
runtime-semantic signals in 99. Builder exclusions are retained for three
public workspaces (clickstream, climate alignment, and fraud triage). Their
presence is dataset evidence requiring case-specific review, not proof that
every exclusion is incorrect or that every missing value should be restored.

## Predeclared next family, and why it is not ready for immediate replay

The reference-only ranking selects the shared seven-service fan-in family:

1. `extension/crm_sales_enrichment_fusion`
2. `extension/supplier_risk_api_table_fusion`
3. `extension/support_profile_context_join`

This covers 81 original IR cells (three workflows × three models × M3–M5 ×
three repetitions), separately from their 81 direct-Argo cells. No model
scores or availability were used in selecting this family.

Its zero reference-input-review count means the **bound manifest file** is
present, not that the public task fully specifies all source roles and
reconciliation behavior. A review of public tasks and fixtures found:

- CRM names a territory lookup table as its third input, but its active
  manifest lists only account JSON and sales CSV. Accounts contain region
  codes; no separate territory lookup or rule deriving one is supplied.
- Supplier risk names a supplier master table, but the active manifest lists
  only risk API JSON and procurement CSV. Those files include supplier fields,
  but no explicit rule says whether they replace the named master source.
- Support names a subscription-plan lookup, while the supplied third input
  is a routing policy. Profiles contain account-tier values and the policy
  contains tier multipliers, but the relationship to the named lookup and
  the required publication semantics needs an explicit public contract.

Each has three source ingestors, a fan-in validator, normalizer, reconciler,
and publisher, with generic profiles/`any` bundles. Join keys, duplicate and
unmatched-row handling, source precedence, threshold boundaries, output
schemas, and actual third-source roles must be specified from public evidence
before executing a new semantic study. Do not fabricate a missing lookup,
treat a status bundle as a third source, or call the group execution-ready
because its manifest and status schemas exist.

## Recommended progression

Preserve this completed census. The next work should have two explicit lanes,
both possible without buying new generations:

1. **Availability/response diagnosis:** classify the saved responses behind
   the 471 parse-error missing-IR cells, retaining exact original attempt
   order and available usage/finish metadata. Investigate empty/truncated
   output before proposing any conservative, separately labeled extraction
   repair. Record missing metadata as unknown. Do not infer provider behavior
   or recoverability from the two spot checks.
2. **Data/public-contract controls for the preselected family:** resolve or
   document the three-source/public-fixture discrepancies and freeze a
   general fan-in/join contract before implementing seven service operations.
   If public evidence is insufficient for an unchanged task, report that
   limitation. New fixtures/semantics would be a v2 dataset/runtime revision,
   not a retroactive correction of saved model scores. Independently review
   the ten reference parameter mismatches as a v2 data/contract errata list.

Only after those controls should another paired replay be prepared for the
fixed family. The census confirms multiple contributing layers; it does not
establish their causal shares, demonstrate that the original G6-Assert oracle
is numerically wrong, or justify changing submitted semantic results.
