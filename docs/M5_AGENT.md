# M5 agent reproduction notes

M5 is a sandboxed agentic baseline, not the Prompt2ServiceFlow method itself. Its resource budget is matched to M4’s public-feedback opportunities.

The frozen v21/v22 container source is under `experiments/m5/build-v2.1.8/`. A portability-only authoring default in the bundled source-ingestion CLI was changed from an author-local absolute path to `P2SF_SPEC_MATTERS_ROOT`; that CLI is not invoked by M5 and the experimental method is unchanged. The orchestration code builds two images:

- an agent image containing Python, Node, the Pi coding agent, and the Prompt2ServiceFlow package;
- a proxy image that reaches the provider, injects the credential, logs completions, and enforces the cumulative token cap.

The agent container has no general outbound route and sees only a staged public workspace. Gold and hidden evaluation files are absent. A validator shim enforces four calls, derived from M4’s initial validation plus three repairs. Compile calls are not budgeted.

Build the frozen images before a large run:

```bash
python3 scripts/run_m5_agent.py --help
```

The readiness checker verifies the available execution sandbox. `--skip-image-build` is safe only after the exact frozen image version has been built locally. Container/provider failures are resumable infrastructure observations; reaching a step, token, validation, or wall-clock budget is a valid experimental stopping outcome.

