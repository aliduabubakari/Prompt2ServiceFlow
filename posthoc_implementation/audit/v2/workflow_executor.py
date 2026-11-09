"""Closed, fail-closed executor for local file/CSV mechanism controls.

Consumes explicit bindings, topologically orders control and data dependencies,
and evaluates structured equality gates. It never runs model-supplied code,
queries private answers, fills missing inputs, or falls back to output examples.
This is a declared subset, not a general ServiceFlowIR/Argo implementation.
"""
from __future__ import annotations

import json
import csv
from pathlib import Path

import service_executor as ports
import retention_adapter

VERSION = "2.0.0-candidate.2"
SENSOR = "file_location_availability_sensor"
CSV = "csv_tabular_schema_validating_loader"
EXPORT = "structured_json_to_csv_exporter"
SUPPORTED = {SENSOR, CSV, EXPORT}


def definition(service):
    if service not in SUPPORTED:
        raise ports.UnsupportedOperation(f"Unimplemented workflow service: {service}")
    if service == SENSOR:
        return {"inputs": {"file_location_resource"}, "optional_inputs": set(),
                "outputs": {"availability_decision", "check_status"}}
    return ports.REGISTRY[service]


def compile_plan(plan: dict) -> list[str]:
    if set(plan) - {'workflow_id', 'contract_version', 'artifacts', 'bindings', 'edges', 'gates'}:
        raise ports.UnsupportedOperation('Unimplemented workflow fields')
    if plan.get('contract_version') != '2.1.0':
        raise ValueError('Explicit local workflow contract version required')
    artifacts = {a['artifact_id']: a for a in plan['artifacts']}
    bindings = {b['intent_id']: b for b in plan['bindings']}
    if not bindings or len(bindings) != len(plan['bindings']) or len(artifacts) != len(plan['artifacts']):
        raise ValueError('Empty or duplicate binding/artifact declarations')
    for artifact in artifacts.values():
        ports.identifier(artifact['artifact_id'])
        if artifact['suffix'] not in ('.csv', '.json'):
            raise ports.UnsupportedOperation('Only explicit CSV/JSON artifacts are supported')
    dependencies = {i: set() for i in bindings}
    seen_outputs = set()
    for intent, binding in bindings.items():
        ports.identifier(intent)
        if binding['service_version'] != '1.0.0':
            raise ports.UnsupportedOperation('Exact supported service version required')
        desc = definition(binding['service_id'])
        if binding.get('secret_bindings'):
            raise ports.UnsupportedOperation('Secret-dependent invocation unsupported')
        for name, required, allowed in [('input_bindings', desc['inputs'], desc['inputs'] | desc['optional_inputs']),
                                        ('output_bindings', desc['outputs'], desc['outputs'])]:
            names = [x['port'] for x in binding.get(name, [])]
            if len(names) != len(set(names)) or not required.issubset(names) or not set(names).issubset(allowed):
                raise ValueError(f'Invalid service ports: {intent}')
        for item in binding['output_bindings']:
            artifact = artifacts[item['artifact_id']]
            ports.identifier(artifact['artifact_id'])
            if artifact['producer'] != intent or artifact['artifact_id'] in seen_outputs:
                raise ValueError('Output producer mismatch or multiple output writers')
            seen_outputs.add(artifact['artifact_id'])
        for item in binding['input_bindings']:
            artifact = artifacts[item['artifact_id']]
            producer = artifact.get('producer')
            if producer:
                if producer not in bindings:
                    raise ValueError('Input has an absent producer')
                dependencies[intent].add(producer)
            elif not artifact.get('fixture_ref'):
                raise ValueError('External input requires an explicit public fixture binding')
    for artifact in artifacts.values():
        if artifact.get('producer') and artifact['artifact_id'] not in seen_outputs:
            raise ValueError('Declared produced artifact has no bound writer')
    for edge in plan.get('edges', []):
        if set(edge) != {'from', 'to'}:
            raise ports.UnsupportedOperation('Conditional/free-text edges are unsupported')
        if edge['from'] not in bindings or edge['to'] not in bindings:
            raise ValueError('Unknown control dependency')
        dependencies[edge['to']].add(edge['from'])
    for gate in plan.get('gates', []):
        if set(gate) != {'artifact_id', 'field', 'equals', 'targets'} or not isinstance(gate['equals'], bool):
            raise ports.UnsupportedOperation('Only explicit Boolean equality gates are supported')
        artifact = artifacts[gate['artifact_id']]
        if (not artifact.get('producer') or not isinstance(gate['field'], str)
                or not isinstance(gate['targets'], list) or not gate['targets']):
            raise ValueError('Gate needs a produced artifact and explicit field')
        for target in gate['targets']:
            if target not in bindings:
                raise ValueError('Gate references unknown target')
            dependencies[target].add(artifact['producer'])
    order = []
    pending = set(bindings)
    while pending:
        ready = sorted(i for i in pending if dependencies[i].issubset(order))
        if not ready:
            raise ValueError('Workflow dependency cycle')
        order.extend(ready)
        pending.difference_update(ready)
    return order


def input_value(artifact: dict, workspace: Path, fixtures: Path):
    if artifact.get('producer'):
        path = ports.inside(workspace, 'artifacts/' + artifact['artifact_id'] + artifact['suffix'])
    else:
        relative = retention_adapter.fixture_relative(artifact['fixture_ref'])
        path = ports.inside(fixtures, relative.as_posix())
    raw = path.read_text(encoding='utf-8')
    return raw if artifact['suffix'] == '.csv' else json.loads(raw)


def sensor(parameters: dict, resource: dict, fixtures: Path) -> dict:
    if set(parameters) - {'location_type', 'path', 'availability_condition'}:
        raise ports.UnsupportedOperation('Unsupported filesystem sensor parameter')
    if (parameters.get('location_type') != 'filesystem' or resource != {'driver': 'fixture-filesystem', 'root': '.'}
            or parameters.get('availability_condition') != 'exists'):
        raise ports.UnsupportedOperation('Only the explicitly declared fixture filesystem/exists profile is supported')
    path = ports.inside(fixtures, parameters['path'])
    exists = path.is_file()
    return {'availability_decision': {'available': exists, 'condition': 'exists', 'path': parameters['path'],
                                      'candidate_count': int(exists)},
            'check_status': {'success': True, 'location_type': 'filesystem', 'path_checked': parameters['path'], 'errors': []}}


def execute(plan: dict, workspace: Path, fixtures: Path) -> dict:
    order = compile_plan(plan)  # Reject unsupported services before any task writes.
    artifacts = {a['artifact_id']: a for a in plan['artifacts']}
    bindings = {b['intent_id']: b for b in plan['bindings']}
    states, trace = {}, []
    for intent in order:
        binding = bindings[intent]
        parents = {e['from'] for e in plan.get('edges', []) if e['to'] == intent}
        parents.update(artifacts[x['artifact_id']]['producer'] for x in binding['input_bindings']
                       if artifacts[x['artifact_id']].get('producer'))
        if any(states[p] != 'executed' for p in parents):
            states[intent] = 'skipped'
            trace.append({'intent_id': intent, 'state': 'skipped', 'reason': 'upstream_not_executed'})
            continue
        try:
            permitted = True
            for gate in plan.get('gates', []):
                if intent not in gate['targets']:
                    continue
                producer = artifacts[gate['artifact_id']]['producer']
                if states.get(producer) != 'executed':
                    permitted = False
                    break
                decision = input_value(artifacts[gate['artifact_id']], workspace, fixtures)
                value = decision[gate['field']]
                if not isinstance(value, bool):
                    raise ValueError('Gate result must be Boolean')
                if value != gate['equals']:
                    permitted = False
            if not permitted:
                states[intent] = 'skipped'
                trace.append({'intent_id': intent, 'state': 'skipped', 'reason': 'public_gate_false'})
                continue
            inputs = {i['port']: input_value(artifacts[i['artifact_id']], workspace, fixtures)
                      for i in binding['input_bindings']}
            uris = {i['port']: artifacts[i['artifact_id']].get('fixture_ref', 'artifact:' + i['artifact_id'])
                    for i in binding['input_bindings']}
            service, parameters = binding['service_id'], binding['parameter_bindings']
            values = (sensor(parameters, inputs['file_location_resource'], fixtures) if service == SENSOR else
                      ports.compute(service, parameters, inputs, uris))
            outputs = [{'port': i['port'], 'artifact_id': i['artifact_id'],
                        'suffix': artifacts[i['artifact_id']]['suffix']} for i in binding['output_bindings']]
            spec = {'intent_id': intent, 'service_id': service, 'parameters': parameters, 'outputs': outputs}
            writes, mapping = ports.plan_writes(spec, values)
            writes.pop('logs/public_output_bindings.json')
            writes['logs/bindings/' + intent + '.json'] = (json.dumps(mapping, indent=2) + '\n').encode()
            targets = {key: ports.inside(workspace, key) for key in writes}
            if any(path.exists() for path in targets.values()):
                raise ValueError('A workflow task would overwrite an existing artifact')
            for key, path in targets.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(writes[key])
            states[intent] = 'executed'
            trace.append({'intent_id': intent, 'state': 'executed', 'service_id': service})
        except (ValueError, KeyError, OSError, TypeError, csv.Error) as exc:
            states[intent] = 'failed'
            trace.append({'intent_id': intent, 'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'})
    result = {'executor_version': VERSION, 'states': states, 'trace': trace,
              'workflow_status': 'failed' if 'failed' in states.values() else 'completed'}
    target = ports.inside(workspace, 'logs/workflow_trace.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result
