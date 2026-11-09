"""Strict original-IR binding adapter for the declared six-stage profile."""
from __future__ import annotations

import json
from pathlib import Path
import re
import bounded_window_ops as ops
import retention_adapter

OPERATIONS = {
    'bounded_timeseries_event_ingestor': ('ingest_bounded_events', ops.ingest),
    'bounded_window_checkpoint_validator': ('validate_checkpoint_inputs', ops.validate),
    'timeseries_record_sort_deduplicator': ('sort_and_deduplicate_records', ops.deduplicate),
    'bounded_analysis_window_builder': ('build_analysis_windows', ops.window),
    'window_metric_aggregator': ('compute_window_metrics', ops.aggregate),
    'timeseries_output_bundle_publisher': ('publish_outputs', ops.publish),
}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', value):
        raise ValueError('Unsafe/unsupported artifact or intent identifier')
    return value


def compile_ir(ir):
    bindings = {b['intent_id']: b for b in ir['bindings']}
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    intents = [i['intent_id'] for i in ir['service_intents']]
    if (len(bindings) != len(ir['bindings']) or len(artifacts) != len(ir['artifacts'])
            or len(intents) != len(set(intents)) or set(intents) != set(bindings)):
        raise ValueError('Duplicate or unmatched IR identifiers')
    if sorted(b['service_id'] for b in bindings.values()) != sorted(OPERATIONS):
        raise ops.Unsupported('This profile requires each of the six exact operations once')
    flow = ir['control_flow']
    if set(flow) - {'edges', 'branches', 'gates', 'parallel_groups'}:
        raise ops.Unsupported('Unknown control-flow semantics')
    if flow.get('branches') or flow.get('gates') or flow.get('parallel_groups'):
        raise ops.Unsupported('Branch/parallel semantics outside this linear profile')
    parents, writers = {i: set() for i in bindings}, set()
    for intent, binding in bindings.items():
        identifier(intent)
        if binding['service_version'] != '1.0.0' or binding.get('secret_bindings'):
            raise ops.Unsupported('Unverified service version or secret-dependent binding')
        for field, required in [('input_bindings', {'input_artifacts'}), ('output_bindings', {'output_artifacts', 'execution_report'})]:
            values = [v['port'] for v in binding.get(field, [])]
            if len(values) != len(set(values)) or set(values) != required:
                raise ops.Unsupported('Profile requires one explicit input bundle and two exact output ports')
        parameters = binding.get('parameter_bindings', {})
        if set(parameters) - {'operation_profile', 'modality_policy'}:
            raise ops.Unsupported('Unknown operation parameter semantics')
        if parameters.get('operation_profile') != OPERATIONS[binding['service_id']][0]:
            raise ops.Unsupported('Operation profile label outside this declared public interpretation')
        policy = parameters.get('modality_policy', {})
        if set(policy) - {'batch', 'true_streaming'} or policy.get('true_streaming', False) is not False:
            raise ops.Unsupported('Unknown modality policy or true streaming is unsupported')
        for item in binding['output_bindings']:
            a = artifacts[item['artifact_id']]
            identifier(a['artifact_id'])
            if (a.get('media_type') not in (None, 'application/json') or
                    a.get('data_type') not in ('any', 'json', 'object', 'table', 'status')):
                raise ops.Unsupported('Only explicitly JSON-shaped bound artifacts are supported')
            if a.get('producer') != intent or a['artifact_id'] in writers:
                raise ValueError('Output writer mismatch')
            writers.add(a['artifact_id'])
        a = artifacts[binding['input_bindings'][0]['artifact_id']]
        producer = a.get('producer')
        if producer:
            if not isinstance(producer, str) or producer not in parents:
                raise ops.Unsupported('Unresolved or multi-producer input')
            parents[intent].add(producer)
        elif not a.get('fixture_ref'):
            raise ops.Unsupported('External fixture link missing; no binding repair permitted')
    for edge in flow.get('edges', []):
        if set(edge) != {'from', 'to'} or edge['from'] not in parents or edge['to'] not in parents:
            raise ops.Unsupported('Malformed/conditional original edge is not translated')
        parents[edge['to']].add(edge['from'])
    for a in artifacts.values():
        if a.get('producer') and a['artifact_id'] not in writers:
            raise ValueError('Produced artifact has no actual writer')
    order, pending = [], set(bindings)
    while pending:
        ready = sorted(i for i in pending if parents[i].issubset(order))
        if not ready:
            raise ValueError('Dependency cycle')
        order.extend(ready)
        pending.difference_update(ready)
    return order, parents


def execute(ir, profile, workspace, fixtures):
    ops.verify_profile(profile)
    order, parents = compile_ir(ir)
    bindings = {b['intent_id']: b for b in ir['bindings']}
    artifacts = {a['artifact_id']: a for a in ir['artifacts']}
    states, events = {}, []
    for intent in order:
        if any(states[p] != 'executed' for p in parents[intent]):
            states[intent] = 'skipped'
            events.append({'intent_id': intent, 'state': 'skipped'})
            continue
        binding = bindings[intent]
        try:
            a = artifacts[binding['input_bindings'][0]['artifact_id']]
            path = (ops.contained(workspace, 'artifacts/' + identifier(a['artifact_id']) + '.json') if a.get('producer') else
                    ops.contained(fixtures, retention_adapter.fixture_relative(a['fixture_ref']).as_posix()))
            payload = json.loads(path.read_text())
            operation = OPERATIONS[binding['service_id']][1]
            if operation is ops.ingest:
                output = operation(payload, fixtures, profile)
            elif operation is ops.publish:
                output = operation(payload, profile, workspace, intent)
            else:
                output = operation(payload, profile)
            for item in binding['output_bindings']:
                target = ops.contained(workspace, 'artifacts/' + identifier(item['artifact_id']) + '.json')
                if target.exists():
                    raise ValueError('Attempted artifact overwrite')
                value = output if item['port'] == 'output_artifacts' else {
                    'success': True, 'errors': [], 'counts': output.get('counts', {}), 'service_id': binding['service_id']}
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value, indent=2) + '\n')
            states[intent] = 'executed'
            events.append({'intent_id': intent, 'state': 'executed', 'service_id': binding['service_id']})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            states[intent] = 'failed'
            events.append({'intent_id': intent, 'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
    trace = {'states': states, 'events': events, 'workflow_status': 'failed' if 'failed' in states.values() else 'completed'}
    target = ops.contained(workspace, 'logs/bounded_window_trace.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(trace, indent=2) + '\n')
    return trace
