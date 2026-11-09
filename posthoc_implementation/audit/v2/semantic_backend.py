"""Explicit semantic runtime registry; no mock fallback or profile-label repair.

The implementation supports a declared operation family, not pipeline/model ids.
Package compilation and live execution are separate entry points.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil

import bounded_window_ops as ops
import paired_window_executor as window
import retention_adapter

BACKEND_ID = 'p2sf.semantic.window/1'
SUPPORTED_PROFILE = 'bounded-window-1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def verify_profile(profile):
    if set(profile) != {'profile_version', 'input_keys', 'fields', 'rules'}:
        raise ops.Unsupported('Only the declared public runtime-profile fields are supported')
    if profile['profile_version'] != SUPPORTED_PROFILE:
        raise ops.Unsupported('No registered implementation for this profile version')
    if set(profile['input_keys']) != {'records', 'registry'}:
        raise ops.Unsupported('Explicit records and registry input roles are required')
    if set(profile['fields']) != {'entity', 'group', 'time', 'energy', 'demand', 'quality', 'capacity'}:
        raise ops.Unsupported('Unknown or missing public field roles')
    if not all(isinstance(v, str) and v for mapping in (profile['fields'], profile['input_keys']) for v in mapping.values()):
        raise ops.Unsupported('Public role mappings must be explicit nonempty field names')
    ops.verify_profile(profile)


def compile_plan(ir, profile):
    verify_profile(profile)
    intents = {row['intent_id']: row for row in ir['service_intents']}
    artifacts = {row['artifact_id']: row for row in ir['artifacts']}
    consumers = defaultdict(set)
    for binding in ir['bindings']:
        service = binding['service_id']
        if service not in window.OPERATIONS or binding['service_version'] != '1.0.0':
            raise ops.Unsupported('No registered implementation for this service/version')
        required_label = window.OPERATIONS[service][0]
        if binding.get('parameter_bindings', {}).get('operation_profile') != required_label:
            raise ops.Unsupported('Operation label does not match the declared public profile; no relabeling')
        intent = intents[binding['intent_id']]
        for field, ports in [('inputs', 'input_bindings'), ('outputs', 'output_bindings')]:
            if set(intent[field]) != {p['artifact_id'] for p in binding[ports]}:
                raise ValueError('Redundant intent list disagrees with actual port bindings')
        for port in binding['output_bindings']:
            if port['port'] == 'output_artifacts' and artifacts[port['artifact_id']].get('data_type') not in ('any', 'json', 'object'):
                raise ops.Unsupported('Bound computation artifacts must declare JSON bundles; published CSV is a separate file')
        for port in binding['input_bindings']:
            artifact = artifacts[port['artifact_id']]
            consumers[port['artifact_id']].add(binding['intent_id'])
            if not artifact.get('producer'):
                reference = artifact.get('fixture_ref')
                if (artifact.get('role') != 'input' or artifact.get('data_type') not in ('any', 'json', 'object')
                        or not isinstance(reference, str) or not reference.startswith('fixtures/inputs/')):
                    raise ops.Unsupported('External input needs an explicit scenario-neutral JSON fixture link')
                relative = retention_adapter.fixture_relative(reference)
                if relative.suffix != '.json':
                    raise ops.Unsupported('The input-bundle contract requires a JSON manifest')
    for identity, artifact in artifacts.items():
        if set(artifact['consumers']) != consumers[identity]:
            raise ValueError('Artifact consumers disagree with actual port bindings')
    plan = window.compile_plan(ir)
    if any(row['original_label'] != row['external_operation'] for row in plan['profile_overrides']):
        raise ValueError('Dispatch would reinterpret an undeclared operation label')
    return {**plan, 'backend_id': BACKEND_ID, 'profile_version': profile['profile_version'],
            'strict_labels_verified': True, 'label_replacements': [], 'mock_fallback': False}


def execute(ir, profile, workspace, fixtures):
    plan = compile_plan(ir, profile)
    # The existing controlled executor performs the actual data operations.
    # Exact-label checks above prevent its compatibility mode from assigning
    # a new meaning to an arbitrary model-produced profile string.
    result = window.execute(ir, profile, workspace, fixtures)
    receipt = {'backend_id': BACKEND_ID, 'profile_version': profile['profile_version'],
               'profile_sha256': digest(profile), 'ir_sha256': digest(ir),
               'strict_labels_verified': True, 'label_replacements': [], 'mock_fallback': False,
               'workflow_status': result['workflow_status'],
               'service_versions': {b['service_id']: b['service_version'] for b in ir['bindings']}}
    target = ops.contained(workspace, 'logs/semantic_backend_receipt.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2) + '\n')
    return {**result, 'semantic_backend': receipt}


def materialize_runtime(ir, profile, scenarios, destination, schema):
    """Export a new trusted runtime package; never replace an existing package."""
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema).validate(ir)
    plan = compile_plan(ir, profile)
    if (not scenarios or len({s['name'] for s in scenarios}) != len(scenarios)
            or any(set(s) != {'name', 'parameters', 'fixture_root'} or s['parameters'] != {} for s in scenarios)):
        raise ops.Unsupported('Require explicit unique fixture scenarios; runtime parameter interpolation is not supported')
    for scenario in scenarios:
        window.strict.identifier(scenario['name'])
        ops.contained(Path('/semantic-package'), scenario['fixture_root'])
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Semantic compiler requires a new output directory')
    scripts = destination / 'runtime/scripts'
    scripts.mkdir(parents=True)
    source = Path(__file__).resolve().parent
    for name in ('semantic_backend.py', 'paired_window_executor.py', 'bounded_window_executor.py', 'bounded_window_ops.py'):
        shutil.copy2(source / name, scripts / name)
    shutil.copy2(source.parent / 'retention_adapter.py', scripts / 'retention_adapter.py')
    for name, value in [('ir.json', ir), ('profile.json', profile), ('compile_receipt.json', plan)]:
        (scripts / name).write_text(json.dumps(value, indent=2) + '\n')
    (scripts / 'workflow.py').write_text(
        'import argparse,json\nfrom pathlib import Path\nfrom semantic_backend import execute\n'
        'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path)\n'
        'a=p.parse_args();root=Path(__file__).parent\n'
        'r=execute(json.loads((root/"ir.json").read_text()),json.loads((root/"profile.json").read_text()),a.workspace,a.fixtures)\n'
        'print(json.dumps(r));raise SystemExit(0 if r["workflow_status"]=="completed" else 2)\n')
    manifest = {'runtime_manifest_version': '0.1.0', 'pipeline_id': ir['composition_id'],
                'image': 'python:3.12-slim', 'workflow_parameters': [],
                'tasks': [{'intent_id': 'semantic_workflow', 'script': 'scripts/workflow.py',
                           'arguments': ['--workspace', '{workspace}', '--fixtures', '{fixtures}'], 'retries': 0}],
                'scenarios': scenarios}
    import yaml
    (destination / 'runtime/manifest.yaml').write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest
