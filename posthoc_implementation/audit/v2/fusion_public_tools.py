"""Second-family adapter; frozen v27 public tools remain unchanged."""
from __future__ import annotations

import json
from pathlib import Path
import sys

# The image entry point uses this file as semantic_public_tools.py. The old
# implementation is shipped under its own versioned name for transparent reuse.
if __name__ == 'semantic_public_tools':
    import semantic_public_tools_v27 as previous
else:
    import semantic_public_tools as previous
import fusion_backend
import fusion_completion
import fusion_stage_runtime

base = previous.clone_module(previous, '_p2sf_relational_public_tools')
base.VERSION = 'p2sf.public-relational-methods/1'
base.backend = fusion_backend
base.semantic_completion = fusion_completion
base.semantic_stage_runtime = fusion_stage_runtime


def deployment_sources():
    old_names = ('retention_adapter', 'bounded_window_ops', 'bounded_window_executor', 'paired_window_executor',
                 'semantic_backend', 'semantic_stage_runtime', 'binding_assembly', 'semantic_completion')
    sources = {name: Path(sys.modules[name].__file__).read_text() for name in old_names}
    sources.update({name: Path(sys.modules[name].__file__).read_text() for name in ('fusion_ops', 'fusion_backend', 'fusion_completion', 'fusion_stage_runtime')})
    sources['semantic_public_tools_v27'] = Path(previous.__file__).read_text()
    sources['semantic_public_tools'] = Path(__file__).read_text()
    return sources


def task_script(ir, profile, intent):
    sources = {name: deployment_sources()[name] for name in ('retention_adapter', 'fusion_ops', 'fusion_backend', 'fusion_stage_runtime')}
    return ('import sys,types,json,argparse\nfrom pathlib import Path\n'
        + 'sources=' + repr(sources) + '\n'
        + 'for name,source in sources.items():\n'
          ' m=types.ModuleType(name);m.__file__=__file__;sys.modules[name]=m;exec(compile(source,name,"exec"),m.__dict__)\n'
        + 'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path);a=p.parse_args()\n'
        + 'from fusion_stage_runtime import execute_stage\n'
        + 'ok=execute_stage(json.loads(' + repr(json.dumps(ir)) + '),json.loads(' + repr(json.dumps(profile))
        + '),' + repr(intent) + ',a.workspace,a.fixtures)\nraise SystemExit(0 if ok else 2)\n')


base.task_script = task_script
base.deployment_sources = deployment_sources
VERSION, CONTRACT = base.VERSION, base.CONTRACT
PUBLIC_MODULES = tuple(deployment_sources())
backend, original_submission = fusion_backend, previous.original_submission
clone_module, checked_plan = base.clone_module, base.checked_plan
materialize_runtime, validate_submission = base.materialize_runtime, base.validate_submission
compile_submission, main = base.compile_submission, base.main


if __name__ == '__main__': raise SystemExit(main())
