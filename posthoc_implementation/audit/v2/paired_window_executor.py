"""Declared v2 interpretation, not a claim about undocumented v1 profiles.

Dispatch uses registered service identity and a fixed external profile. Original
parameter strings and all binding identities are retained in the plan/trace.
"""
from __future__ import annotations

import json
from pathlib import Path

import bounded_window_executor as strict
import bounded_window_ops as ops
import retention_adapter

OPERATIONS = strict.OPERATIONS


def outputs(binding, artifacts):
    data = [o for o in binding['output_bindings'] if o['port'] == 'output_artifacts']
    reports = [o for o in binding['output_bindings'] if o['port'] == 'execution_report']
    if len(reports) != 1 or len(data) not in (1, 2) or len(data) + len(reports) != len(binding['output_bindings']):
        raise ops.Unsupported('Supported outputs: one primary bundle, one status, optional publisher audit projection')
    auxiliary = []
    if len(data) == 2:
        if binding['service_id'] != 'timeseries_output_bundle_publisher':
            raise ops.Unsupported('Multiple intermediate data outputs have unspecified projections')
        auxiliary = [o for o in data if artifacts[o['artifact_id']].get('role') == 'report'
                     and artifacts[o['artifact_id']].get('data_type') in ('json', 'object')]
        primary = [o for o in data if artifacts[o['artifact_id']].get('role') == 'output'
                   and artifacts[o['artifact_id']].get('data_type') in ('table', 'json', 'object', 'any')]
        if len(auxiliary) != 1 or len(primary) != 1 or primary[0] == auxiliary[0]:
            raise ops.Unsupported('Multiple publisher artifacts need one explicit output and one JSON report role')
    else:
        primary = data
        artifact = artifacts[primary[0]['artifact_id']]
        if artifact.get('role') not in ('intermediate', 'output') or artifact.get('data_type') not in ('any', 'json', 'object', 'table'):
            raise ops.Unsupported('Primary bundle must have explicit intermediate/output role and JSON-compatible computation type')
    status = artifacts[reports[0]['artifact_id']]
    if status.get('data_type') != 'status' or status.get('role') not in ('status', 'report'):
        raise ops.Unsupported('Execution report requires explicit status type and status/report role')
    return primary[0]['artifact_id'], reports[0]['artifact_id'], [o['artifact_id'] for o in auxiliary]


def compile_plan(ir):
    """Reuse strict graph checks via a documented dispatch view, not IR edits."""
    import copy
    view = copy.deepcopy(ir)
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    if len(artifacts) != len(ir['artifacts']):
        raise ValueError('Duplicate artifact identities')
    projections, overrides = {}, []
    for original, binding in zip(ir['bindings'], view['bindings']):
        service = original['service_id']
        if service not in OPERATIONS:
            raise ops.Unsupported('Service identity is not implemented')
        parameters = original.get('parameter_bindings', {})
        if not isinstance(parameters.get('operation_profile'), str):
            raise ops.Unsupported('An original string operation_profile is required')
        primary, status, audit = outputs(original, artifacts)
        projections[original['intent_id']] = {'primary': primary, 'status': status, 'audit': audit}
        overrides.append({'intent_id': original['intent_id'], 'service_id': service,
                          'original_label': parameters['operation_profile'], 'external_operation': OPERATIONS[service][0],
                          'meaning': 'explicit_v2_override_not_proven_equivalence'})
        binding['parameter_bindings']['operation_profile'] = OPERATIONS[service][0]
        binding['output_bindings'] = [o for o in binding['output_bindings'] if o['artifact_id'] not in audit]
        view['artifacts'] = [a for a in view['artifacts'] if a['artifact_id'] not in audit]
        for identity in audit:
            if artifacts[identity].get('consumers') or any(i['artifact_id'] == identity for b in ir['bindings'] for i in b['input_bindings']):
                raise ops.Unsupported('Projected audit reports cannot feed computation in this subset')
    order, parents = strict.compile_ir(view)
    # Validate writers for every projected artifact too, rather than discarding
    # their original binding checks along with the dispatch view.
    writers = set()
    for binding in ir['bindings']:
        for output in binding['output_bindings']:
            identity = strict.identifier(output['artifact_id']); a = artifacts[identity]
            if identity in writers or a.get('producer') != binding['intent_id']:
                raise ValueError('Conflicting or inconsistent output writers')
            if a.get('media_type') not in (None, 'application/json'):
                raise ops.Unsupported('Only JSON-shaped bound projections are implemented')
            writers.add(identity)
    return {'order': order, 'parents': {k: sorted(v) for k, v in parents.items()},
            'outputs': projections, 'profile_overrides': overrides}


def execute(ir, profile, workspace, fixtures):
    ops.verify_profile(profile)
    plan = compile_plan(ir)
    bindings = {b['intent_id']: b for b in ir['bindings']}
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    states, events = {}, []
    for intent in plan['order']:
        if any(states[p] != 'executed' for p in plan['parents'][intent]):
            states[intent] = 'skipped'; events.append({'intent_id': intent, 'state': 'skipped'}); continue
        binding = bindings[intent]
        try:
            artifact = artifacts[binding['input_bindings'][0]['artifact_id']]
            path = (ops.contained(workspace, 'artifacts/' + strict.identifier(artifact['artifact_id']) + '.json') if artifact.get('producer') else
                    ops.contained(fixtures, retention_adapter.fixture_relative(artifact['fixture_ref']).as_posix()))
            payload = json.loads(path.read_text())
            operation = OPERATIONS[binding['service_id']][1]
            if operation is ops.ingest:
                value = operation(payload, fixtures, profile)
            elif operation is ops.publish:
                value = operation(payload, profile, workspace, intent)
            else:
                value = operation(payload, profile)
            projection = plan['outputs'][intent]
            values = {projection['primary']: value, projection['status']: {
                'success': True, 'errors': [], 'counts': value.get('counts', {}), 'service_id': binding['service_id']}}
            for identity in projection['audit']:
                values[identity] = json.loads(ops.contained(workspace, value['published_files']['audit']).read_text())
            for identity, content in values.items():
                target = ops.contained(workspace, 'artifacts/' + strict.identifier(identity) + '.json')
                if target.exists():
                    raise ValueError('Output overwrite is not allowed')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(content, indent=2) + '\n')
            states[intent] = 'executed'; events.append({'intent_id': intent, 'state': 'executed', 'service_id': binding['service_id']})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            states[intent] = 'failed'; events.append({'intent_id': intent, 'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
    trace = {'states': states, 'events': events, 'workflow_status': 'failed' if 'failed' in states.values() else 'completed',
             'profile_overrides': plan['profile_overrides'], 'output_projections': plan['outputs']}
    target = ops.contained(workspace, 'logs/bounded_window_trace.json'); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(trace, indent=2) + '\n')
    return trace
