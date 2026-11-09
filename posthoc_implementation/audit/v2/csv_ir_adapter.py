"""Bounded, host-only CSV IR execution projection; no model code execution.

This is a new runtime intervention, not an implementation of Argo policies,
G0-G6 or the M5 agent/tool route. No missing graph, binding or parameter is
completed. The caller must separately validate the full IR before any later
saved-output replay. Controls use independently authored execution projections.
"""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from jsonschema import Draft202012Validator
import csv_postgres_ops as ops
import csv_replay_eligibility as public
import service_executor as kernels

VERSION = 'p2sf.csv-ir-projection/1'
SENSOR, CSV, SNAPSHOT, TABULAR = public.SENSOR, public.VALIDATOR, ops.SNAPSHOT, ops.TABULAR
Error = ops.ContractError


def require(condition, code, message):
    if not condition: raise Error(code, message)


def digest(value): return hashlib.sha256(ops.canonical_bytes(value)).hexdigest()


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,100}', value),
            'unsafe_identity', 'Require a bounded artifact/intent identity')
    return value


def checked_schema(schema):
    stack = [schema]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            require(not any(k in value and (not isinstance(value[k], str) or not value[k].startswith('#'))
                            for k in ('$ref', '$dynamicRef')), 'nonlocal_schema', 'Only internal schema references are allowed')
            require('$id' not in value, 'nonlocal_schema', 'Schema base-URI changes are not supported')
            stack.extend(value.values())
        elif isinstance(value, list): stack.extend(value)
    Draft202012Validator.check_schema(schema)


def target_name(value, default_schema):
    require(isinstance(value, str), 'unsupported_target', 'Explicit target table required')
    parts = value.split('.')
    require(len(parts) in (1, 2), 'unsupported_target', 'Use table or schema.table, without SQL expressions')
    if len(parts) == 1: parts.insert(0, default_schema)
    for part in parts: ops.ident(part)
    return tuple(parts)


def parameters(service, p):
    require(isinstance(p, dict) and not public.contains_template(p), 'unresolved_parameters', 'Parameters must be explicit; templates are not evaluated')
    if service == SENSOR:
        require(not set(p) - {'location_type', 'path', 'availability_condition', 'filename_pattern', 'recursive'}, 'unsupported_sensor', 'Unknown sensor option')
        require(p.get('location_type') == 'filesystem' and p.get('recursive', False) is False,
                'unsupported_sensor', 'Only bounded nonrecursive filesystem sensing is implemented')
        require(p.get('availability_condition') in ('exists', 'contains_matching_files'), 'unsupported_sensor', 'Unsupported availability condition')
        kernels.logical_path(p.get('path'))
        if 'filename_pattern' in p:
            value = p['filename_pattern']
            require(isinstance(value, str) and 0 < len(value) < 256 and not any(c in value for c in ('/', '\\', '\0', '{', '}', '$'))
                    and value not in ('.', '..') and '**' not in value, 'unsupported_glob', 'Require a bounded basename glob')
        if p['availability_condition'] == 'contains_matching_files':
            require('filename_pattern' in p, 'missing_glob', 'Do not infer a filename pattern')
    elif service == CSV:
        require(not set(p) - {'required_columns', 'has_header', 'delimiter', 'fail_on_empty', 'output_path'},
                'unsupported_validation', 'Typed schemas and unknown CSV parameters need a separate implementation')
        required = p.get('required_columns')
        require(isinstance(required, list) and required and len(required) == len(set(required)),
                'missing_required_columns', 'This condition requires explicit nonempty unique validation columns')
        for name in required: ops.ident(name)
        require(p.get('has_header', True) is True and p.get('delimiter', ',') == ',' and
                isinstance(p.get('fail_on_empty', False), bool), 'unsupported_validation', 'Require headered comma CSV and boolean flags')
        kernels.logical_path(p.get('output_path'))
    else:
        allowed = {'import_spec', 'load_mode', 'target_label', 'delimiter', 'has_header'} if service == SNAPSHOT else {'target_table', 'write_mode'}
        require(not set(p) - allowed, 'unsupported_loader', 'Unknown loader parameter is not discarded')
        mode = p.get('load_mode') if service == SNAPSHOT else p.get('write_mode')
        require(mode in ('append', 'replace'), 'unsupported_write_mode', 'Explicit append/replace only; never infer upsert keys')
        if service == SNAPSHOT:
            spec = p.get('import_spec')
            require(isinstance(spec, dict) and set(spec) <= {'target_table', 'columns'} and 'target_table' in spec,
                    'unsupported_import_spec', 'Only target_table and explicit identity columns are supported')
            if 'columns' in spec:
                require(isinstance(spec['columns'], list) and spec['columns'] and len(set(spec['columns'])) == len(spec['columns']),
                        'unsupported_columns', 'Identity columns must be explicit and unique')
                for c in spec['columns']: ops.ident(c)
            require(p.get('has_header', True) is True and p.get('delimiter', ',') == ',', 'unsupported_loader', 'Headered comma CSV only')
            if 'target_label' in p:
                require(isinstance(p['target_label'], str) and 0 < len(p['target_label']) <= 200,
                        'unsupported_target_label', 'Target label is descriptive, never a connection address')


def compile_projection(ir, intervention, schemas):
    """Check the execution slice without filling anything in the source IR."""
    raw = copy.deepcopy(ir); spec = copy.deepcopy(intervention); schemas = copy.deepcopy(schemas)
    require(spec.get('version') == VERSION and spec.get('execution') == 'single_attempt_reference',
            'undeclared_intervention', 'An explicit single-attempt mock-to-reference intervention is required')
    require(isinstance(raw, dict) and isinstance(raw.get('runtime'), dict) and
            raw['runtime'].get('execution_profile') in spec.get('accepted_source_profiles', []),
            'undeclared_profile', 'Original profile must be named in the intervention')
    def index(rows, key):
        require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), 'bad_arrays', key)
        names = [identity(r.get(key)) for r in rows]
        require(len(set(names)) == len(names), 'duplicate_identity', key)
        return dict(zip(names, rows))
    artifacts = index(raw.get('artifacts'), 'artifact_id')
    intents = index(raw.get('service_intents'), 'intent_id')
    bindings = index(raw.get('bindings'), 'intent_id')
    require(set(bindings) == set(intents) and len(bindings) == 3, 'unsupported_roster', 'Exactly three explicit intents/bindings required')
    services = [b.get('service_id') for b in bindings.values()]
    require(sorted(services) in (sorted([SENSOR, CSV, SNAPSHOT]), sorted([SENSOR, CSV, TABULAR])),
            'unsupported_roster', 'Require sensor, CSV validator and one registered loader')
    consumers = {a: set() for a in artifacts}; writers = {}; nodes = {}
    for name, b in bindings.items():
        service = b['service_id']; parameters(service, b.get('parameter_bindings'))
        require(b.get('service_version') == '1.0.0' and not b.get('secret_bindings'), 'unsupported_binding', 'No unsupported version or secret-dependent binding')
        node = {'service': service, 'parameters': b['parameter_bindings']}
        for direction, expected in zip(('input', 'output'), public.PORTS[service]):
            rows = b.get(direction + '_bindings')
            require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), 'bad_ports', name)
            links = {r.get('port'): r.get('artifact_id') for r in rows}
            require(len(links) == len(rows) and set(links) == set(expected), 'bad_ports', name + ':' + direction)
            declared = intents[name].get(direction + 's')
            require(isinstance(declared, list) and len(declared) == len(set(declared)) and set(declared) == set(links.values()), 'intent_port_mismatch', name)
            for port, aid in links.items():
                require(aid in artifacts and artifacts[aid].get('data_type') == expected[port], 'port_type_mismatch', name + ':' + str(port))
                if direction == 'input': consumers[aid].add(name)
                else:
                    require(aid not in writers and artifacts[aid].get('producer') == name, 'writer_mismatch', aid)
                    writers[aid] = name
                    ref = artifacts[aid].get('schema_ref')
                    require(isinstance(ref, str) and ref in schemas, 'missing_output_schema', aid)
                    checked_schema(schemas[ref])
            node[direction + 's'] = links
        nodes[name] = node
    resources = spec.get('fixtures', {})
    for aid, a in artifacts.items():
        require(set(a.get('consumers', [])) == consumers[aid] and len(a.get('consumers', [])) == len(consumers[aid]), 'consumer_mismatch', aid)
        if aid not in writers:
            require(a.get('producer') is None and a.get('fixture_ref') in resources, 'missing_fixture_link', aid)
            entry = resources[a['fixture_ref']]
            require(entry.get('kind') in ('csv', 'filesystem', 'database'), 'unsupported_resource', aid)
            if a['data_type'] == 'csv': require(entry['kind'] == 'csv', 'resource_type_mismatch', aid)
    flow = raw.get('control_flow')
    require(isinstance(flow, dict) and not flow.get('branches') and not flow.get('parallel_groups'), 'unsupported_flow', 'No inferred branch or parallel execution')
    parents = {name: set() for name in nodes}
    for edge in flow.get('edges', []):
        require(isinstance(edge, dict) and set(edge) == {'from', 'to'} and edge['from'] in nodes and edge['to'] in nodes,
                'bad_edge', 'Undeclared or conditional edge')
        require(edge['from'] not in parents[edge['to']], 'duplicate_edge', 'Duplicate edge')
        parents[edge['to']].add(edge['from'])
    order, remaining = [], set(nodes)
    while remaining:
        ready = sorted(n for n in remaining if parents[n] <= set(order))
        require(ready, 'cycle', 'Cyclic graph')
        order.extend(ready); remaining.difference_update(ready)
    ancestors = {}
    for n in order: ancestors[n] = parents[n] | set().union(*(ancestors[p] for p in parents[n]))
    by_service = {n['service']: i for i, n in nodes.items()}; sensor = by_service[SENSOR]; validator = by_service[CSV]
    loader = next(i for i, n in nodes.items() if n['service'] in (SNAPSHOT, TABULAR))
    require(sensor in ancestors[validator] and validator in ancestors[loader], 'unsupported_dependency', 'Sensor → validator → loader must already be declared')
    for n, node in nodes.items():
        for aid in node['inputs'].values():
            if aid in writers: require(writers[aid] in ancestors[n], 'missing_dependency', aid)
    gates = flow.get('gates')
    require(isinstance(gates, list) and len(gates) == 1, 'unsupported_gate', 'Require one explicit sensor gate')
    gate = gates[0]; decision = nodes[sensor]['outputs']['availability_decision']
    require(gate.get('sensor_intent') == sensor and gate.get('condition') == decision + '.available == true'
            and isinstance(gate.get('gated_intents'), list) and validator in gate['gated_intents']
            and set(gate['gated_intents']) <= (set(nodes) - {sensor}), 'unsupported_gate', 'Only the declared availability predicate is interpreted')
    # The source runtime and policies are preserved and recorded, not silently
    # implemented by this one-attempt business-operation projection.
    plan = {'version': VERSION, 'source_ir_sha256': digest(raw), 'source_ir': raw,
            'intervention': spec, 'schemas': schemas, 'nodes': nodes, 'artifacts': artifacts,
            'order': order, 'parents': {n: sorted(p) for n, p in parents.items()}, 'gate': gate,
            'not_executed': {k: raw[k] for k in ('schedule', 'policies', 'runtime') if k in raw},
            'full_ir_validation': 'separate prerequisite for saved-output replay; not certified here'}
    plan['plan_sha256'] = digest(plan)
    return plan


def fixture_bytes(spec, root, ref, *, allow_missing=False, csv_only=True):
    entry = spec['fixtures'][ref]
    if csv_only: require(entry.get('kind') == 'csv', 'resource_type_mismatch', ref)
    path = ops.inside(root, entry['path'])
    require(not path.is_symlink(), 'unsafe_fixture', ref)
    if allow_missing and not path.exists():
        require(entry['sha256'] == 'MISSING', 'fixture_hash_mismatch', ref)
        return None
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == entry['sha256'], 'fixture_hash_mismatch', ref)
    return data


def sense(parameters, mount, workspace):
    root_label = mount['logical_root']; kernels.logical_path(root_label)
    logical = parameters['path']; kernels.logical_path(logical)
    base, target = PurePosixPath(root_label), PurePosixPath(logical)
    require(target.is_absolute() == base.is_absolute() and target.is_relative_to(base), 'unmapped_sensor_path', logical)
    directory = ops.inside(workspace, 'mounted_files')
    relative = target.relative_to(base)
    actual = ops.inside(directory, relative.as_posix())
    if parameters['availability_condition'] == 'contains_matching_files':
        matches = sorted(p.name for p in actual.iterdir() if p.is_file() and not p.is_symlink()
                         and fnmatch.fnmatchcase(p.name, parameters['filename_pattern'])) if actual.is_dir() else []
        available = bool(matches)
    else:
        available = actual.exists(); matches = []
        if 'filename_pattern' in parameters and actual.is_dir():
            matches = sorted(p.name for p in actual.iterdir() if p.is_file() and fnmatch.fnmatchcase(p.name, parameters['filename_pattern']))
            available = bool(matches)
    return {'availability_decision': {'available': available, 'reason': 'bounded local filesystem observation', 'matches': matches},
            'check_status': {'success': True, 'errors': []}}


def execute(plan, database, fixture_root, workspace):
    """Run only registered kernels. Never interpret source scripts or SQL."""
    require(plan['version'] == VERSION and digest(plan['source_ir']) == plan['source_ir_sha256'] and
            digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) == plan.get('plan_sha256'),
            'changed_plan', 'Source or execution plan changed since compilation')
    workspace = Path(workspace); workspace.mkdir(parents=True, exist_ok=False)
    spec, arts = plan['intervention'], plan['artifacts']; values = {}; events = []
    for ref, entry in spec['fixtures'].items():
        if entry['kind'] != 'csv': fixture_bytes(spec, fixture_root, ref, csv_only=False)
    # Every mounted byte is an explicit intervention choice. Neither sensor
    # path nor a uniquely available file is used to infer a CSV input binding.
    sensor_node = next(n for n in plan['nodes'].values() if n['service'] == SENSOR)
    sensor_ref = arts[sensor_node['inputs']['file_location_resource']]['fixture_ref']
    mount = spec['fixtures'][sensor_ref]
    require(mount['kind'] == 'filesystem', 'resource_type_mismatch', sensor_ref)
    mounted = workspace / 'mounted_files'; mounted.mkdir()
    require(len(mount['files']) <= 100, 'mount_limit', 'At most 100 explicitly named files')
    for name, ref in mount['files'].items():
        require(isinstance(name, str) and PurePosixPath(name).name == name and name not in ('.', '..'), 'unsafe_mount', str(name))
        data = fixture_bytes(spec, fixture_root, ref, allow_missing=True)
        if data is not None: ops.inside(mounted, name).write_bytes(data)
    states = {}; written = {}; loader_called = False; load_status = None
    for intent in plan['order']:
        node = plan['nodes'][intent]; service = node['service']; p = node['parameters']
        blocked = any(states[parent] != 'completed' for parent in plan['parents'][intent])
        if intent in plan['gate']['gated_intents']:
            decision_id = plan['nodes'][plan['gate']['sensor_intent']]['outputs']['availability_decision']
            blocked = blocked or not values.get(decision_id, {}).get('available', False)
        if blocked:
            states[intent] = 'skipped_dependency_or_gate'; events.append({'intent': intent, 'state': states[intent]}); continue
        def ref(port): return arts[node['inputs'][port]]['fixture_ref']
        if service == SENSOR: result = sense(p, mount, workspace)
        elif service == CSV:
            raw = fixture_bytes(spec, fixture_root, ref('csv_file'))
            try:
                result = kernels.compute(CSV, p, {'csv_file': raw.decode('utf-8')}, {'csv_file': ref('csv_file')})
            except (ValueError, UnicodeError) as exc: raise Error('csv_validation_failed', str(exc)) from exc
            for c in result['validated_dataset']['columns']: ops.ident(c)
            dataset_id = node['outputs']['validated_dataset']; encoded = ops.canonical_bytes(result['validated_dataset'])
            result['validated_data_object'].update(contract_version='p2sf-tabular-object/1', dataset_ref='artifacts/' + dataset_id + '.json', dataset_sha256=hashlib.sha256(encoded).hexdigest())
        else:
            entry = spec['fixtures'][ref('target_database')]
            require(entry['kind'] == 'database', 'resource_type_mismatch', 'target_database')
            resource = copy.deepcopy(entry['resource']); ops.check_resource(resource)
            name = p['import_spec']['target_table'] if service == SNAPSHOT else p['target_table']
            schema, table = target_name(name, resource['schema'])
            require(schema in entry['allowed_schemas'], 'unmapped_target_schema', schema)
            resource['schema'] = schema
            if service == SNAPSHOT:
                data = ops.validated(fixture_bytes(spec, fixture_root, ref('csv_snapshot')), [], fail_on_empty=False)['validated_dataset']
                if 'columns' in p['import_spec']:
                    require(p['import_spec']['columns'] == data['columns'], 'nonidentity_columns', 'Column list must exactly match actual ordered CSV header')
                loader_called = True
                status = ops.write_dataset(database, resource, table, data, p['load_mode'])
                result = {'target_database_reference': {'target_table': name, 'rows_imported': status['rows_written'],
                    'database': resource['database'], 'schema': schema, 'table': table}, 'load_status': status}
            else:
                loader_called = True
                result = ops.load_tabular(database, resource, workspace, values[node['inputs']['ingested_data_object']],
                                          {'target_table': table, 'write_mode': p['write_mode']})
            result['load_status'].update(rows_loaded=result['load_status']['rows_written'], logical_target_table=name)
            if 'target_label' in p: result['target_database_reference']['target_label'] = p['target_label']
            load_status = result['load_status']
        # Do not project away properties to make a schema pass. Actual port
        # values must conform to their original declared local schemas.
        for port, aid in node['outputs'].items():
            try: Draft202012Validator(plan['schemas'][arts[aid]['schema_ref']]).validate(result[port])
            except Exception as exc: raise Error('output_schema_mismatch', aid + ': ' + str(exc)) from exc
        for port, aid in node['outputs'].items():
            values[aid] = result[port]; location = 'artifacts/' + aid + '.json'; encoded = ops.canonical_bytes(result[port])
            path = ops.inside(workspace, location); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(encoded)
            written[aid] = {'path': location, 'sha256': hashlib.sha256(encoded).hexdigest()}
        if service == CSV:
            aid = node['outputs']['validated_dataset']
            alias = 'service_outputs/' + intent + '/validated_dataset/' + kernels.logical_path(p['output_path'])
            dest = ops.inside(workspace, alias); dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(ops.inside(workspace, written[aid]['path']).read_bytes())
            written[aid].update(logical_location=p['output_path'], materialized_alias=alias)
        states[intent] = 'completed'; events.append({'intent': intent, 'state': 'completed', 'service': service})
    receipt = {'adapter_version': VERSION, 'source_ir_sha256': plan['source_ir_sha256'], 'intervention_sha256': digest(spec),
               'state': 'loaded' if loader_called else 'skipped_missing_input', 'loader_called': loader_called,
               'events': events, 'outputs': written, 'load_status': load_status, 'not_executed': plan['not_executed'],
               'source_ir_unchanged': digest(plan['source_ir']) == plan['source_ir_sha256']}
    (workspace / 'receipt.json').write_bytes(ops.canonical_bytes(receipt))
    return receipt
