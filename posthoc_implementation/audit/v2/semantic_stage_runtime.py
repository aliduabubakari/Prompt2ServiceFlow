"""One registered real service per task; no oracle or model-generated code."""
from __future__ import annotations

import json
from pathlib import Path

import semantic_backend as backend


def execute_stage(ir, profile, intent, workspace, fixtures):
    plan = backend.compile_plan(ir, profile)
    if intent not in plan['order']:
        raise ValueError('Unknown intent')
    workspace, fixtures = Path(workspace), Path(fixtures)
    trace_path = backend.ops.contained(workspace, 'logs/bounded_window_trace.json')
    if trace_path.exists():
        previous = json.loads(trace_path.read_text())
        if previous.get('ir_sha256') != backend.digest(ir) or previous.get('profile_sha256') != backend.digest(profile):
            raise ValueError('Stale or unrelated runtime state')
        states, events = previous['states'], previous['events']
    else:
        states, events = {name: 'skipped' for name in plan['order']}, []
    if states[intent] != 'skipped' or any(states[parent] != 'executed' for parent in plan['parents'][intent]):
        raise ValueError('Stage already attempted or dependency not executed')
    binding = next(b for b in ir['bindings'] if b['intent_id'] == intent)
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    try:
        source = artifacts[binding['input_bindings'][0]['artifact_id']]
        path = (backend.ops.contained(workspace, 'artifacts/' + source['artifact_id'] + '.json') if source.get('producer') else
                backend.ops.contained(fixtures, backend.retention_adapter.fixture_relative(source['fixture_ref']).as_posix()))
        payload = json.loads(path.read_text())
        operation = backend.window.OPERATIONS[binding['service_id']][1]
        if operation is backend.ops.ingest:
            value = operation(payload, fixtures, profile)
        elif operation is backend.ops.publish:
            value = operation(payload, profile, workspace, intent)
        else:
            value = operation(payload, profile)
        projection = plan['outputs'][intent]
        outputs = {projection['primary']: value, projection['status']: {
            'success': True, 'errors': [], 'counts': value.get('counts', {}), 'service_id': binding['service_id']}}
        for identity in projection['audit']:
            outputs[identity] = json.loads(backend.ops.contained(workspace, value['published_files']['audit']).read_text())
        for identity, content in outputs.items():
            target = backend.ops.contained(workspace, 'artifacts/' + identity + '.json')
            if target.exists():
                raise ValueError('Output overwrite is not allowed')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(content, indent=2) + '\n')
        states[intent] = 'executed'
        events.append({'intent_id': intent, 'state': 'executed', 'service_id': binding['service_id']})
    except (ValueError, KeyError, TypeError, OSError) as exc:
        states[intent] = 'failed'
        events.append({'intent_id': intent, 'state': 'failed', 'error': type(exc).__name__ + ': ' + str(exc)})
    status = 'failed' if 'failed' in states.values() else 'completed' if all(v == 'executed' for v in states.values()) else 'in_progress'
    trace = {'states': states, 'events': events, 'workflow_status': status,
             'profile_overrides': plan['profile_overrides'], 'ir_sha256': backend.digest(ir), 'profile_sha256': backend.digest(profile)}
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2) + '\n')
    receipt = {'backend_id': backend.BACKEND_ID, 'profile_version': profile['profile_version'],
               'profile_sha256': backend.digest(profile), 'ir_sha256': backend.digest(ir),
               'strict_labels_verified': True, 'label_replacements': [], 'mock_fallback': False,
               'workflow_status': status, 'service_versions': {b['service_id']: b['service_version'] for b in ir['bindings']}}
    backend.ops.contained(workspace, 'logs/semantic_backend_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return states[intent] == 'executed'
