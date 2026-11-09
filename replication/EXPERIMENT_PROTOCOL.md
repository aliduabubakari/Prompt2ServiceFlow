# Experimental and accounting protocol

Three repetitions are averaged within each pipeline, then 110 pipelines are
macro-averaged. The original primary study has 5,940 cells and the five-condition
Qwen ablation has 1,650 cells. Generation records are immutable.

M4 uses the Python client with temperature 0.2, top-p 1 and seeds 101/202/303.
M5 uses Pi; configured decoding metadata is not necessarily forwarded. Its
nominal 12-step threshold counts turn-end events, while API attempts count
proxy completion records and successful responses require HTTP 200.
Overruns are 36/2/64 for DeepSeek-Flash/Qwen-480B/Qwen-27B, maximum 15 steps.
The sensitivity audit inspects actions after the step-12 boundary; it is not
an independently rerun strict-budget experiment.

Cost is `(input_tokens * input_rate + completion_tokens * output_rate)/1e6`.
Input/output rates are USD 0.14/0.42 for DeepSeek-Flash and USD 0.30/1.00 for
Qwen-480B per million tokens. No cache discounts are applied to the standardized
column. Provider estimates remain separate, and reasoning tokens are already
part of completion tokens. Failed requests with no usage are not assigned
invented charges. SINTEF prices are unavailable.

Qwen-27B retains 3,651 observed HTTP-200 responses; an incomplete log loses
responses witnessed by eleven successful assistant messages. The supported
minimum is 3,661/330 = 11.09394, displayed as 11.09 with a lower-bound annotation
in the final PDF. The observed 11.06 proxy mean is retained as a separate field.

Cumulative gate survival uses the evaluation-time gate vector of the final
retained M4 submission; every preceding gate must pass for the same artifact.
Missing outcomes are non-survival. Do not combine passes from different repairs.

The Qwen-480B M2–M4 sensitivity instead requires the recorded G0, G1, G2 and
G5 statuses to pass (10/330 M2 and 292/330 M4). Cumulative survival through G5
also requires G3 and G4 (201/330 M4). Direct-Argo and IR-derived checks are
representation-specific. G4 in the evaluated implementation checks secret
bindings and network policy compatibility.
