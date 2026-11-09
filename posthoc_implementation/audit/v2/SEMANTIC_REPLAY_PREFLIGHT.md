# Frozen semantic replay preflight

Freeze: `p2sf-semantic-replay-v2.1`.
The actual CLI preflight passed implementation, source-evidence and freeze
verification. The relevant test suite passed 82 tests. No model calls or saved
workflow executions were performed during preparation.

All 5,940 original cells are retained. M0–M2 account for 2,970 direct-Argo
observations, which have no execution route in this IR backend.

| Original M3–M5 observation state | Cells |
|---|---:|
| Missing saved IR | 741 |
| Unreadable or invalid saved IR | 17 |
| No reviewed public task/numerical-profile association | 2,191 |
| Reviewed task, incompatible explicit execution contract | 21 |
| Ready to execute under the frozen contract | **0** |
| Total original IR observations | **2,970** |

Within the 21 incompatible observations, all 21 select the mock runtime,
20 have operation labels that do not match the registered implementation,
five have inconsistent source identities, and one has an unregistered
service/version. These blocker counts overlap.

The successful later v2 generation was given the explicit public execution
contract; it is not an original experimental cell. Its six positive passes and
three correct rejections do not establish that older saved outputs can be
executed faithfully under this contract.

Running the batch command will persist the full coverage ledger, checkpoints
and model/method summaries, with zero eligible executions and no semantic-rate
estimate. It will not resolve missing semantic meaning in old profile labels.
No override, label translation, runtime-choice replacement or private-reference
substitution is enabled. This is an applicability limit, not a measured
zero-percent semantic-success rate.

Further semantic measurement requires reviewed real implementations/public
execution contracts for more service families, with new generation under those
contracts registered as a separate v2 experiment. Any experiment assigning new
meanings to older saved labels must instead state that intervention explicitly.
Original v1 results, paper, deposit and earlier audits remain unchanged.
