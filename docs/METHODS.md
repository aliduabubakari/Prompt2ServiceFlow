# Experimental methods

All methods receive only their declared public workspace view. Gold mappings, labels, assertions, and private evaluation material are excluded from prompts and agent workspaces.

| Method | Description | Output |
|---|---|---|
| M0 | Direct2Argo: one language-model call maps the task description directly to an Argo workflow. | Argo YAML |
| M1 | Prompt2DAG-Argo: the model first creates a generic DAG and then translates it to Argo. | DAG JSON and Argo YAML |
| M2 | Catalogue-Grounded Argo: the model receives the frozen candidate/catalog context and directly creates Argo. | Argo YAML |
| M3 | Contract-first ServiceFlowIR: the model creates ServiceFlowIR, followed by deterministic runtime and Argo projection. | ServiceFlowIR plus compiled runtime |
| M4 | M3 with bounded public-validator repair. The frozen budget is three repairs after the initial validation. | Best-ranked valid or partially valid ServiceFlowIR submission |
| M5 | A sandboxed tool-using coding agent with filesystem access to a public per-instance workspace, compile and validation tools, and matched validation budget. | Agent-authored ServiceFlowIR submission |

M4 selects candidates lexicographically by overall public pass, consecutive passed gate prefix, total passed gates, and fewer diagnostics. A regression cannot replace a better earlier candidate.

M5 runs in an isolated container with no direct provider credential. A host-side proxy injects the credential, accounts for usage, and records calls. The agent has a 12-step limit, a four-call validator budget, a wall-clock timeout, and a frozen token cap. Reaching a declared budget is a valid method outcome; provider and container failures are infrastructure observations that must be resumed rather than scored.

## Evaluation gates

| Gate | Purpose |
|---|---|
| G0 | Parse and schema validity |
| G1 | Referential and graph consistency |
| G2 | Catalogue grounding and binding validity |
| G3 | Contract compatibility |
| G4 | Policy and lifecycle compliance |
| G5 | Compilation/deployment-readiness validation |
| G6-Exec | Sandboxed execution of generated runtime artifacts |
| G6-Assert | Scenario-specific semantic assertions |

M0--M2 do not produce the ServiceFlowIR/runtime package required by G3, G4, or G6. Those gates and end-to-end pass are not applicable to them. Their graph, grounding, common-gate, compilation, and efficiency measures remain valid.

