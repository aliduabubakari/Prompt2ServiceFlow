# Review of the completed protocol-13 probe

Evidence: `audit/outputs/package_v2_reasoning_probe__20261025T145941Z__f731fb39`.
The run is complete, with source inputs unchanged. Verified all 50,880 input
fingerprints and both completed request/response/result inventories.

| Condition | Exact JSON | Finish | Final characters | Recorded reasoning characters | Prompt tokens | Completion tokens |
|---|---|---|---:|---:|---:|---:|
| Default | yes | stop | 24 | 239 | 30 | 60 |
| reasoning_effort: none | yes | stop | 24 | 0 | 32 | 9 |

The second response has no reasoning field. Both responses are within the
requested 512-token limit. The setting has an observed effect on this small
request; neither HTTP acceptance alone nor the server fingerprint is being
treated as proof of support. These observations do not determine the maximum
effective token capacity or prove why every historical response was empty.

The preceding protocol-12 IR requests both ended at a length limit, with empty
final content and recorded reasoning text. The next useful test is the exact
same full/compact public IR request pair with only `reasoning_effort: none`
added. Protocol 14 records this as a new serving configuration, retains the
16,384-token requested budget, and compares it against the preserved pair.
It performs no semantic execution or repair. A later method comparison must
use the same declared serving configuration for all methods; do not pool this
new configuration silently into original SINTEF results.

The tiny probe is a transport/serving control, not a semantic benchmark result.
The token reduction applies to this probe. Its response times are not evidence
of general speed gains: there is one request per condition and cached prompt
tokens differ. Keep v1, original results, and submitted paper unchanged.
