"""Shared public compiler/validator for v2 M3, M4 and Pi M5.

This module and its deployment bundle contain no business oracle, reference
composition, private fixture variants, or submitted-paper scorer.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

import yaml
from jsonschema import Draft202012Validator
from prompt2serviceflow.experiments import submission as original_submission
import semantic_backend as backend
import semantic_completion
import semantic_stage_runtime

VERSION = 'p2sf.public-real-methods/1'
CONTRACT = 'v2_contract.json'
PUBLIC_MODULES = ('retention_adapter', 'bounded_window_ops', 'bounded_window_executor',
                  'paired_window_executor', 'semantic_backend', 'semantic_stage_runtime',
                  'binding_assembly', 'semantic_completion', 'semantic_public_tools')


def clone_module(original, name):
    spec = importlib.util.spec_from_file_location(name, original.__file__)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def deployment_sources():
    return {name: Path(sys.modules[name].__file__).read_text() for name in PUBLIC_MODULES}


def catalog_get(workspace, service, version):
    catalog = original_submission._catalog_index(workspace / 'catalog')
    descriptor = catalog.get((service, version))
    return descriptor, None if descriptor else 'public_descriptor_unavailable'


def contract_at(workspace):
    contract = json.loads((workspace / CONTRACT).read_text())
    if contract.get('version') != VERSION:
        raise ValueError('Unknown public execution contract')
    backend.verify_profile(contract['profile'])
    semantic_completion.validate_contract(contract['projection'])
    return contract


def checked_plan(ir, profile):
    plan = backend.compile_plan(ir, profile)
    for binding in ir['bindings']:
        policy = binding.get('parameter_bindings', {}).get('modality_policy', {})
        if 'batch' in policy and policy['batch'] is not True:
            raise ValueError('This public implementation requires bounded batch execution when modality is declared')
    declared = {(e['from'], e['to']) for e in ir['control_flow']['edges']}
    required = {(parent, intent) for intent, parents in plan['parents'].items() for parent in parents}
    if declared != required:
        raise ValueError('Declare data dependencies explicitly in control_flow; no hidden runtime edges are added')
    return plan


def task_script(ir, profile, intent):
    # The original Argo compiler ships task scripts only. Embed the small
    # standard-library runtime bundle so the resulting Argo has no missing
    # local imports or unmounted JSON sidecar dependencies.
    names = ('retention_adapter', 'bounded_window_ops', 'bounded_window_executor',
             'paired_window_executor', 'semantic_backend', 'semantic_stage_runtime')
    sources = {name: deployment_sources()[name] for name in names}
    return ('import sys,types,json,argparse\nfrom pathlib import Path\n'
        + 'sources=' + repr(sources) + '\n'
        + 'for name,source in sources.items():\n'
          ' m=types.ModuleType(name);m.__file__=__file__;sys.modules[name]=m;exec(compile(source,name,"exec"),m.__dict__)\n'
        + 'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path);a=p.parse_args()\n'
        + 'from semantic_stage_runtime import execute_stage\n'
        + 'ok=execute_stage(json.loads(' + repr(json.dumps(ir)) + '),json.loads(' + repr(json.dumps(profile))
        + '),' + repr(intent) + ',a.workspace,a.fixtures)\nraise SystemExit(0 if ok else 2)\n')


def materialize_runtime(workspace, submission):
    workspace, submission = Path(workspace), Path(submission)
    runtime = submission / 'runtime'
    argo = submission / 'argo'
    # A failed new compilation must not leave a stale earlier package.
    for target in (runtime, argo):
        if target.exists(): shutil.rmtree(target)
    contract = contract_at(workspace)
    raw = yaml.safe_load((submission / 'serviceflow.yaml').read_text())
    schema = json.loads((workspace / 'schemas/serviceflow_ir.schema.json').read_text())
    Draft202012Validator(schema).validate(raw)
    if any(raw.get(key) != value for key, value in contract['metadata'].items()):
        raise ValueError('Public source/catalog bookkeeping differs from the supplied contract')
    if raw.get('runtime', {}).get('execution_profile') != 'reference':
        raise ValueError('Explicit reference runtime required; mock/production are not reinterpreted')
    completed, decision = semantic_completion.complete(raw, lambda s, v: catalog_get(workspace, s, v),
                                                       contract['projection'], contract['assembly_policy'])
    if decision['state'] == 'blocked_no_changes':
        raise ValueError('Ambiguous compiler completion: ' + decision['reason'])
    Draft202012Validator(schema).validate(completed)
    plan = checked_plan(completed, contract['profile'])
    source_id = backend.digest(raw)
    history = submission / 'v2_compilation' / source_id
    history.mkdir(parents=True, exist_ok=True)
    for name, value in [('raw_ir.json', raw), ('effective_ir.json', completed), ('completion.json', decision)]:
        path = history / name
        if path.exists() and json.loads(path.read_text()) != value:
            raise ValueError('Compilation history changed')
        path.write_text(json.dumps(value, indent=2) + '\n')
    # This declared elaboration is common to all three methods. Raw responses
    # and raw IR are retained; the validator/controller sees the canonical IR.
    (submission / 'serviceflow.yaml').write_text(yaml.safe_dump(completed, sort_keys=False))
    scripts = runtime / 'scripts'; scripts.mkdir(parents=True)
    tasks = []
    for intent in plan['order']:
        name = intent + '.py'
        (scripts / name).write_text(task_script(completed, contract['profile'], intent))
        tasks.append({'intent_id': intent, 'script': 'scripts/' + name,
            'arguments': ['--workspace', '{workspace}', '--fixtures', '{fixtures}'],
            'dependencies': sorted(edge['from'] for edge in completed['control_flow']['edges'] if edge['to'] == intent), 'retries': 0})
    manifest = {'runtime_manifest_version': '0.1.0', 'pipeline_id': completed['composition_id'],
        'image': 'python:3.12-slim', 'workflow_parameters': [], 'tasks': tasks,
        'scenarios': [{'name': 'nominal', 'parameters': {}, 'fixture_root': 'fixtures/scenarios/nominal'}]}
    Draft202012Validator(json.loads((workspace / 'schemas/runtime_manifest.schema.json').read_text())).validate(manifest)
    (runtime / 'manifest.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def compatible_any_diagnostics(context, diagnostics):
    """Versioned JSON-bundle compatibility; retain every other G3 diagnostic."""
    ignored = set()
    if not context.serviceflow_valid:
        return diagnostics
    artifacts = {a['artifact_id']: a for a in context.serviceflow['artifacts']}
    catalog = context.load_catalog()
    for binding in context.serviceflow['bindings']:
        descriptor = catalog.get((binding['service_id'], binding['service_version']))
        if not descriptor: continue
        for direction in ('input', 'output'):
            ports = {p['name']: p for p in descriptor['interface'][direction + 's']}
            for bound in binding[direction + '_bindings']:
                artifact = artifacts.get(bound['artifact_id'])
                port = ports.get(bound['port'])
                if artifact and port and port['data_type'] == 'any' and artifact['data_type'] in ('json', 'object'):
                    ignored.add(('G3_' + direction.upper() + '_TYPE_MISMATCH',
                        f"{binding['intent_id']}: {direction} {bound['port']!r} expects any, got {artifact['data_type']}"))
    return [d for d in diagnostics if (d['code'], d['message']) not in ignored]


def submission_module():
    module = clone_module(original_submission, '_p2sf_v2_public_submission')
    original_g3 = module._gate_g3
    def gate(context):
        diagnostics = compatible_any_diagnostics(context, original_g3(context))
        if context.serviceflow_valid:
            try:
                contract = contract_at(context.workspace_dir)
                if context.serviceflow.get('runtime', {}).get('execution_profile') != 'reference':
                    raise ValueError('Explicit reference runtime required')
                if any(context.serviceflow.get(k) != v for k, v in contract['metadata'].items()):
                    raise ValueError('Incorrect public bookkeeping')
                checked_plan(context.serviceflow, contract['profile'])
            except (ValueError, KeyError, TypeError) as exc:
                diagnostics.append(module._diagnostic('V2_EXECUTION_CONTRACT', str(exc)))
        return diagnostics
    module._gate_g3 = gate
    module.materialize_runtime = materialize_runtime
    module.TOOL_VERSION = VERSION
    return module


def validate_submission(workspace, submission=None, *, run_execution=True):
    report = submission_module().validate_submission(Path(workspace), Path(submission) if submission else None,
                                                     run_execution=run_execution)
    # Retain the exact public feedback for both M4 and M5. No numerical oracle
    # or private input bank is consulted by this tool.
    target = (Path(submission) if submission else Path(workspace) / 'submission') / 'v2_public_reports'
    target.mkdir(parents=True, exist_ok=True)
    index = len(list(target.glob('*.json')))
    (target / f'{index:04d}.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def compile_submission(workspace, submission=None):
    return submission_module().compile_submission(Path(workspace), Path(submission) if submission else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['compile', 'validate'])
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'compile':
            print(json.dumps(compile_submission(args.workspace)))
            return 0
        report = validate_submission(args.workspace)
        print(json.dumps(report))
        return 0 if report['overall_status'] == 'pass' else 1
    except Exception as exc:
        print('v2 public tool failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
