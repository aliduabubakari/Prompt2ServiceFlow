"""Versioned public input diagnostics; no business oracle or automatic repair."""
from __future__ import annotations

import json
from pathlib import Path
import sys

if __name__ == 'semantic_public_tools':
    import semantic_public_tools_v2_2 as previous
else:
    import fusion_public_tools_v2_2 as previous

clone_module = previous.clone_module
original_submission = previous.original_submission
ops = previous.ops


def backend_source(source):
    old = "raise ops.Unsupported('Three distinct validator inputs; one bundle for other operations')"
    new = ("raise ops.Unsupported(f\"$.bindings[{list(bindings).index(intent)}].input_bindings: \" "
           "f\"{intent} ({b['service_id']}@{b['service_version']}), port input_artifacts: \" "
           "f\"expected exactly {count} distinct artifact binding(s), got {len(incoming)} \" "
           "f\"({len({i['artifact_id'] for i in incoming})} distinct); bind the declared public input(s) in ServiceFlowIR\")")
    if source.count(old) != 1:
        raise ValueError('Frozen backend input check changed; review diagnostics')
    return source.replace(old, new, 1)


backend = clone_module(previous.fusion_backend, '_p2sf_relational_backend_v2_3')
exec(compile(backend_source(Path(previous.fusion_backend.__file__).read_text()), backend.__file__, 'exec'), backend.__dict__)
backend.ops = ops
stage = clone_module(previous.fusion_stage_runtime, '_p2sf_relational_stage_v2_3')
stage.backend = backend
base = clone_module(previous.previous, '_p2sf_relational_public_v2_3')
base.VERSION = 'p2sf.public-relational-methods/3'
base.backend, base.semantic_completion, base.semantic_stage_runtime = backend, previous.fusion_completion, stage
VERSION, CONTRACT = base.VERSION, base.CONTRACT


def input_constraints():
    return {service: {'port': 'input_artifacts', 'required': True,
                     'minimum': 3 if role == 'validate' else 1,
                     'maximum': 3 if role == 'validate' else 1,
                     'distinct_artifacts': True,
                     'source': 'public_manifest' if role in ('primary', 'secondary', 'reference') else 'upstream_bundle'}
            for service, (_, role) in backend.OPERATIONS.items()}


def input_diagnostics(ir):
    """Describe every offending public port without choosing artifacts/edges."""
    rows = []
    constraints = input_constraints()
    for index, binding in enumerate(ir.get('bindings', [])):
        service = binding.get('service_id')
        if service not in constraints: continue
        rule = constraints[service]
        incoming = binding.get('input_bindings', [])
        distinct = len({item['artifact_id'] for item in incoming})
        if (len(incoming) == rule['minimum'] and distinct == rule['minimum']
                and all(item.get('port') == rule['port'] for item in incoming)):
            continue
        path = f'$.bindings[{index}].input_bindings'
        message = (f"{path}: {binding['intent_id']} ({service}@{binding['service_version']}), "
                   f"port {rule['port']}: expected exactly {rule['minimum']} distinct artifact binding(s), "
                   f"got {len(incoming)} ({distinct} distinct). "
                   + ('Declare a JSON input artifact with the public manifest fixture_ref and bind it here. '
                      if rule['source'] == 'public_manifest' else 'Bind the required upstream computation bundle(s). ')
                   + 'Correct ServiceFlowIR and run bin/compile; do not edit derived runtime files.')
        rows.append({'code': 'V2_INPUT_BINDING_CONTRACT', 'path': path, 'message': message,
                     'intent_id': binding['intent_id'], 'service_id': service,
                     'port': rule['port'], 'expected_count': rule['minimum'],
                     'actual_count': len(incoming), 'distinct_count': distinct})
    return rows


def deployment_sources():
    sources = previous.deployment_sources()
    old = "if __name__ == 'semantic_public_tools':"
    new = "if __name__ == 'semantic_public_tools_v2_2':"
    v22 = Path(previous.__file__).read_text()
    if v22.count(old) == 1:
        v22 = v22.replace(old, new, 1)
    elif v22.count(new) != 1:
        raise ValueError('Frozen deployment entry changed')
    sources['semantic_public_tools_v2_2'] = v22
    # Keep the old backend source as the input to the guarded transform. The
    # v2.3 backend in host tools and generated jobs uses the same transform.
    sources['semantic_public_tools'] = Path(__file__).read_text()
    return sources


def task_script(ir, profile, intent):
    sources = {name: deployment_sources()[name] for name in ('retention_adapter', 'fusion_ops', 'fusion_backend', 'fusion_stage_runtime')}
    sources['fusion_backend'] = backend_source(sources['fusion_backend'])
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
old_submission_module = base.submission_module


def submission_module():
    module = old_submission_module()
    old_g0, old_g3 = module._gate_g0, module._gate_g3
    def g0(context):
        diagnostics = old_g0(context)
        # Keep the gate order and its failure. Explain the cause of a missing
        # derived manifest rather than asking the model to create one itself.
        causes = input_diagnostics(context.serviceflow) if context.serviceflow_valid else []
        for item in diagnostics:
            if item['code'] == 'G0_MISSING_FILE' and item.get('path') == 'submission/runtime/manifest.yaml' and causes:
                item['message'] += '; public compilation is blocked by: ' + ' | '.join(c['message'] for c in causes)
        return diagnostics
    def g3(context):
        diagnostics = old_g3(context)
        causes = input_diagnostics(context.serviceflow) if context.serviceflow_valid else []
        if causes:
            # Replace only the duplicate arity exception, retaining unrelated
            # interface, type, policy and bookkeeping failures.
            diagnostics = [d for d in diagnostics if not (d['code'] == 'V2_EXECUTION_CONTRACT'
                and 'expected exactly' in d['message'] and '.input_bindings:' in d['message'])]
            diagnostics.extend(causes)
        return diagnostics
    module._gate_g0, module._gate_g3 = g0, g3
    return module


base.submission_module = submission_module
PUBLIC_MODULES = tuple(deployment_sources())
checked_plan, materialize_runtime = base.checked_plan, base.materialize_runtime
validate_submission, compile_submission, main = base.validate_submission, base.compile_submission, base.main


if __name__ == '__main__': raise SystemExit(main())
