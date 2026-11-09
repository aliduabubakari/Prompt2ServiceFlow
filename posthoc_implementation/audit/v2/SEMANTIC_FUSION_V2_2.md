# Relational v2.2: publisher workspace-path correction

The frozen v2.1 control run passed G0–G5, including Argo lint, and completed six
real operations. The publisher then failed at public G6-Exec. No LLM call was
made and the business checker was not reached. That failed run and every v2.1
implementation, configuration, assertion, input file and freeze remain intact.

## Reproduced defect

The publisher's containment helper resolves its output directory to a canonical
filesystem path. It then incorrectly calls relative_to on that resolved path
using the original, possibly symlinked workspace. On macOS, /var and /private/var
can identify the same directory. Any symlinked workspace reproduces the error:
files are written, but the returned publication bundle cannot be constructed.
Earlier pytest paths were already canonical, so direct-script tests missed it.

The versioned adapter inserts one publisher entry normalization:

```python
workspace = Path(workspace).resolve()
```

The exact old source is retained; an explicit guarded source transformation is
used in both host modules and exported task/image payloads. Every other kernel
operation is unchanged. Containment/escape checks and overwrite prevention
remain enforced. Stage failures are also printed to stderr so future public
G6 errors contain the runtime reason instead of only "no output". This diagnostic
change exposes no private assertions or evaluation variants.

The numerical profile, source roles, routing decisions, six positive cases,
three specific rejections, four mutants, independent oracle, method controllers
and budgets are unchanged. The missing reference-source limitations and the
clarified-contract scope from SEMANTIC_FUSION_EXPERIMENT.md still apply.

## Verification and command

Tests reproduce the old failure, compare canonical/symlinked publication, check
exported scripts and image payloads, retain escape/overwrite rejection, and run
the production public validator/executor on synthetic inputs with temporary
directories deliberately exposed through symlink aliases. This last check
exercises the path behavior omitted by the earlier static G0–G5 test.

```sh
cd /Users/abubakarialidu/Documents/Prompt2ServiceFlow-semantic-audit
.venv/bin/python scripts/run_v2_fusion_v2_2.py --dry-run
caffeinate -ims .venv/bin/python -u scripts/run_v2_fusion_v2_2.py --controls-only
```

Use a fresh v2.2 run, not --resume on the failed v2.1 batch. No API token or
model calls are required for controls. The command must pass public nominal
execution, six positive business cases, three specific input rejections and all
four mutants before inference can be enabled. Do not claim success from the
path fix alone; inspect the new control result.

If controls pass, use the same new script with --build-m5-images, then without
--controls-only for the registered method run. The separate image version
v2.28.2 is required; earlier v2.28.1 images are preserved and cannot silently
satisfy the new image requirement. The new freeze and run manifests pin the
failed-parent evidence and corrected implementation.
