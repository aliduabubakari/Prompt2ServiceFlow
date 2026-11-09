# M5 accounting and step-limit audit

Generated with `python3 -B scripts/audit_m5_accounting.py`. No LLM calls or generated-code execution.

## Successful responses and API attempts

Successful means HTTP 200 in the saved proxy log; this does not require a valid composition.
Failed responses are operational overhead, not successful completions.

| Model | HTTP 200 total | Mean HTTP 200 | Mean recorded attempts | Trace-supported minimum mean | Incomplete logs |
|---|---:|---:|---:|---:|---:|
| DeepSeek-Flash | 3822 | 11.58182 | 11.63333 | 11.58182 | 0 |
| Qwen-27B | 3651 | 11.06364 | 12.49697 | 11.09394 | 1 |
| Qwen-480B | 3947 | 11.96061 | 11.99697 | 11.96061 | 0 |

Qwen-27B's proxy count is incomplete: one run retains one proxy response but eleven accepted assistant messages. The minimum count uses the larger witness count per run; this does not recover missing upstream retries.

## Cost normalization

USD per repetition, using the same frozen input/output rates across methods without cache discounts.
Provider estimates and source manifests remain unchanged; these are not invoices.

| Model | Method | Recorded cost | Standardized cost |
|---|---|---:|---:|
| DeepSeek-Flash | M3 | 0.007838 | 0.007838 |
| DeepSeek-Flash | M4 | 0.019973 | 0.019973 |
| DeepSeek-Flash | M5 | 0.016676 | 0.076001 |
| Qwen-27B | M3 | unavailable | unavailable |
| Qwen-27B | M4 | unavailable | unavailable |
| Qwen-27B | M5 | unavailable | unavailable |
| Qwen-480B | M3 | 0.015797 | 0.015797 |
| Qwen-480B | M4 | 0.048724 | 0.048724 |
| Qwen-480B | M5 | 0.050737 | 0.109038 |

## Step-12 artifact sensitivity

The cutoff is immediately after the recorded step-12 event (the current turn and its tools have finished). All overrun cutoffs have balanced tool-start/end records; no tool is pending there.
This inspects subsequent tool actions; it does not replay a strict-budget controller or infer a new model trajectory.

| Model | Overruns | Maximum steps | Valid overrun runs | All final valid | Inferred valid at step 12 | Unresolved |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek-Flash | 36 | 15 | 31 | 186 | 186 | 0 |
| Qwen-27B | 64 | 15 | 10 | 54 | 54 | 0 |
| Qwen-480B | 2 | 15 | 0 | 5 | 5 | 0 |

After step 12, the only tools are one Qwen-27B cleanup outside submission/, one Qwen-480B read, and one Qwen-480B creation of an empty submission directory. None authors or repairs a submission; the empty-directory run is invalid with or without that directory.
Qwen-27B: 10/64 overrun runs and 44/266 within-threshold runs are valid. All 54 valid submissions were already in place by step 12; inferred validity remains 54/330 (16.36%). This is a trace-based sensitivity conclusion, not a strict-budget experimental result.

## Coverage caveat

[
  {
    "run_id": "m5__main__ftp_vendor_inventory_processor__sintef-qwen3-8-27b-nvfp4__s1__20261003T161628.201292Z__932f7fd1",
    "malformed_proxy_lines": [
      2,
      4
    ],
    "proxy_successes": 1,
    "accepted_assistant_messages": 11,
    "recorded_cumulative_tokens": 441155,
    "surviving_usage_token_sum": 46124
  }
]

All input files are SHA-256 indexed in audit.json. Original records and the manuscript are unchanged.
