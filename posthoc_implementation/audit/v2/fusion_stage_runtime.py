"""Registered fan-in stages with distinct per-intent state files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import fusion_backend as backend


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as handle:
        handle.write(json.dumps(value, indent=2) + '\n'); name = handle.name
    os.replace(name, path)


def execute_stage(ir, profile, intent, workspace, fixtures):
    plan = backend.compile_plan(ir, profile)
    if intent not in plan['order']: raise ValueError('Unknown intent')
    workspace, fixtures = Path(workspace), Path(fixtures)
    directory = backend.ops.contained(workspace, 'logs/fusion_stages')
    directory.mkdir(parents=True, exist_ok=True)
    records = {}
    for identity in plan['order']:
        path = directory / (identity + '.json')
        if path.exists():
            record = json.loads(path.read_text())
            if record['ir_sha256'] != backend.digest(ir) or record['profile_sha256'] != backend.digest(profile): raise ValueError('Stale stage state')
            records[identity] = record
    if any(records.get(p, {}).get('state') != 'executed' for p in plan['parents'][intent]):
        raise ValueError('Dependency not executed')
    # Each concurrent ingestion owns its state; no shared read-modify-write
    # counter or trace determines correctness of the fan-in computation.
    with (directory / (intent + '.started')).open('x') as marker: marker.write('single attempt\n')
    binding = next(b for b in ir['bindings'] if b['intent_id'] == intent)
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    record = {'intent_id': intent, 'service_id': binding['service_id'],
              'ir_sha256': backend.digest(ir), 'profile_sha256': backend.digest(profile)}
    try:
        payloads = []
        for port in binding['input_bindings']:
            a = artifacts[port['artifact_id']]
            path = (backend.ops.contained(workspace, 'artifacts/' + a['artifact_id'] + '.json') if a.get('producer') else
                backend.ops.contained(fixtures, backend.retention_adapter.fixture_relative(a['fixture_ref']).as_posix()))
            payloads.append(backend.ops.strict_json(path.read_text()))
        operation = backend.OPERATIONS[binding['service_id']][1]
        if operation in ('primary', 'secondary', 'reference'):
            value = backend.ops.ingest(payloads[0], fixtures, profile, operation)
        elif operation == 'validate': value = backend.ops.validate(payloads, profile)
        elif operation == 'normalize': value = backend.ops.normalize(payloads[0], profile)
        elif operation == 'reconcile': value = backend.ops.reconcile(payloads[0], profile)
        elif operation == 'publish': value = backend.ops.publish(payloads[0], profile, workspace, intent)
        else: raise backend.ops.Unsupported('No registered operation')
        p = plan['outputs'][intent]
        outputs = {p['primary']: value, p['status']: {'success': True, 'errors': [], 'service_id': binding['service_id'], 'counts': value.get('counts', {})}}
        for identity in p['audit']:
            outputs[identity] = backend.ops.strict_json(backend.ops.contained(workspace, value['published_files']['audit']).read_text())
        for identity, content in outputs.items():
            path = backend.ops.contained(workspace, 'artifacts/' + identity + '.json')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x') as handle: handle.write(json.dumps(content, indent=2, allow_nan=False) + '\n')
        record['state'] = 'executed'
    except (ValueError, KeyError, TypeError, OSError) as exc:
        record.update(state='failed', error=type(exc).__name__ + ': ' + str(exc))
    atomic(directory / (intent + '.json'), record)
    # Re-read completed state after this stage; the final publisher or rejecting
    # validator observes all predecessor files after their processes finish.
    records = {identity: json.loads((directory / (identity + '.json')).read_text()) for identity in plan['order'] if (directory / (identity + '.json')).exists()}
    states = {identity: records.get(identity, {}).get('state', 'skipped') for identity in plan['order']}
    status = 'failed' if 'failed' in states.values() else 'completed' if all(v == 'executed' for v in states.values()) else 'in_progress'
    atomic(workspace / 'logs/fusion_trace.json', {'states': states, 'events': list(records.values()), 'workflow_status': status})
    atomic(workspace / 'logs/fusion_backend_receipt.json', {'backend_id': backend.BACKEND_ID,
        'profile_sha256': backend.digest(profile), 'ir_sha256': backend.digest(ir), 'strict_labels_verified': True,
        'label_replacements': [], 'mock_fallback': False, 'workflow_status': status})
    return record['state'] == 'executed'
