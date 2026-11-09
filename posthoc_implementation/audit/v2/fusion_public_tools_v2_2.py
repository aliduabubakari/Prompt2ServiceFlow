"""Relational runtime v2.2: canonical workspace root before publication.

The failed v2.1 code is retained. Only publisher root normalization and public
failure visibility change; numerical rules and independent assertions do not.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

if __name__ == 'semantic_public_tools':
    import semantic_public_tools_v27 as previous
else:
    import semantic_public_tools as previous
import fusion_ops
import fusion_backend
import fusion_completion
import fusion_stage_runtime


def fixed_source(source):
    before = 'def publish(bundle, profile, workspace, intent):\n'
    after = before + '    workspace = Path(workspace).resolve()\n'
    if source.count(before) != 1:
        raise ValueError('Publisher source changed; review canonical-root fix')
    if after in source:
        return source
    return source.replace(before, after, 1)


ops = previous.clone_module(fusion_ops, '_p2sf_relational_ops_v2_2')
exec(compile(fixed_source(Path(fusion_ops.__file__).read_text()), fusion_ops.__file__, 'exec'), ops.__dict__)
backend = previous.clone_module(fusion_backend, '_p2sf_relational_backend_v2_2')
backend.ops = ops
stage = previous.clone_module(fusion_stage_runtime, '_p2sf_relational_stage_v2_2')
stage.backend = backend
base = previous.clone_module(previous, '_p2sf_relational_public_v2_2')
base.VERSION = 'p2sf.public-relational-methods/2'
base.backend, base.semantic_completion, base.semantic_stage_runtime = backend, fusion_completion, stage


def deployment_sources():
    old = ('retention_adapter', 'bounded_window_ops', 'bounded_window_executor', 'paired_window_executor',
           'semantic_backend', 'semantic_stage_runtime', 'binding_assembly', 'semantic_completion')
    sources = {name: Path(sys.modules[name].__file__).read_text() for name in old}
    sources.update({name: Path(sys.modules[name].__file__).read_text() for name in ('fusion_backend', 'fusion_completion', 'fusion_stage_runtime')})
    sources['fusion_ops'] = fixed_source(Path(fusion_ops.__file__).read_text())
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
        + '),' + repr(intent) + ',a.workspace,a.fixtures)\n'
        + 'if not ok:\n'
          ' trace=json.loads((a.workspace/"logs/fusion_trace.json").read_text())\n'
          ' for event in trace["events"]:\n'
          '  if event.get("state")=="failed":print(event.get("error","stage failed"),file=sys.stderr)\n'
          'raise SystemExit(0 if ok else 2)\n')


base.task_script, base.deployment_sources = task_script, deployment_sources
VERSION, CONTRACT = base.VERSION, base.CONTRACT
PUBLIC_MODULES = tuple(deployment_sources())
original_submission = previous.original_submission
clone_module, checked_plan = base.clone_module, base.checked_plan
materialize_runtime, validate_submission = base.materialize_runtime, base.validate_submission
compile_submission, main = base.compile_submission, base.main


if __name__ == '__main__': raise SystemExit(main())
