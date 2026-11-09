"""Independently authored public execution controls, not recovered model IRs."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
from pathlib import Path

import csv_ir_adapter as adapter


SCHEMA_NAMES = {
    'availability_decision': 'availability_decision.schema.json', 'check_status': 'check_status.schema.json',
    'validated_dataset': 'validated_dataset.schema.json', 'validated_data_object': 'validated_data_object.schema.json',
    'validation_status': 'validation_status.schema.json', 'target_database_reference': 'target_db_reference.schema.json',
    'load_status': 'load_status.schema.json'}


def encode_csv(rows):
    stream = io.StringIO(newline=''); csv.writer(stream, lineterminator='\n').writerows(rows)
    return stream.getvalue().encode()


def authored(raw, loader, fixtures, *, missing=False, logical_output='reports/validated.json', mode='replace'):
    """Build a fresh three-operation control solely from its explicit inputs.

    No model source, reference IR, held-out assertion, task ID or gold graph is
    read here. Columns come from the declared authored control fixture, not a
    repair rule applied to model output. Missing-file controls retain a schema.
    """
    fixtures = Path(fixtures); fixtures.mkdir(parents=True, exist_ok=False)
    header = next(csv.reader(io.StringIO(raw.decode())))
    if not missing: (fixtures / 'payload.csv').write_bytes(raw)
    location = {'driver': 'authored-logical-filesystem', 'path': '/audit/landing'}
    original_target = {'driver': 'authored-logical-database', 'name': 'controlled-postgresql'}
    (fixtures / 'location.json').write_bytes(adapter.ops.canonical_bytes(location))
    (fixtures / 'target.json').write_bytes(adapter.ops.canonical_bytes(original_target))
    fixture_map = {}
    for ref, path, kind in [('control/source', 'payload.csv', 'csv'), ('control/location', 'location.json', 'filesystem'), ('control/target', 'target.json', 'database')]:
        p = fixtures / path
        fixture_map[ref] = {'path': path, 'kind': kind, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else 'MISSING'}
    fixture_map['control/location'].update(logical_root='/audit/landing', files={'batch_17.csv': 'control/source'})
    resource = {'driver': adapter.ops.VERSION, 'engine': 'postgresql', 'database': 'p2sf_controls', 'schema': 'p2sf_adapter'}
    fixture_map['control/target'].update(resource=resource, allowed_schemas=['p2sf_adapter', 'p2sf_other'])
    intervention = {'version': adapter.VERSION, 'execution': 'single_attempt_reference',
        'accepted_source_profiles': ['mock'], 'fixtures': fixture_map,
        'scope': 'Authored mechanism control; resource rebinding and one-attempt execution are explicit interventions.'}
    artifacts = [
        {'artifact_id': 'origin', 'data_type': 'csv', 'producer': None, 'consumers': ['parse'] + (['persist'] if loader == adapter.SNAPSHOT else []), 'fixture_ref': 'control/source'},
        {'artifact_id': 'location', 'data_type': 'object', 'producer': None, 'consumers': ['probe'], 'fixture_ref': 'control/location'},
        {'artifact_id': 'destination', 'data_type': 'object', 'producer': None, 'consumers': ['persist'], 'fixture_ref': 'control/target'}]
    bindings, intents = [], []
    ins = {'probe': {'file_location_resource': 'location'}, 'parse': {'csv_file': 'origin'},
           'persist': {'target_database': 'destination', ('csv_snapshot' if loader == adapter.SNAPSHOT else 'ingested_data_object'):
                       ('origin' if loader == adapter.SNAPSHOT else 'parse_validated_data_object')}}
    params = {
        'probe': {'location_type': 'filesystem', 'path': '/audit/landing', 'availability_condition': 'contains_matching_files', 'filename_pattern': 'batch_*.csv'},
        'parse': {'required_columns': header, 'has_header': True, 'delimiter': ',', 'fail_on_empty': True, 'output_path': logical_output},
        'persist': ({'import_spec': {'target_table': 'p2sf_adapter.records_generic', 'columns': header}, 'load_mode': mode,
                     'has_header': True, 'delimiter': ',', 'target_label': 'authored destination'} if loader == adapter.SNAPSHOT else
                    {'target_table': 'p2sf_adapter.records_generic', 'write_mode': mode})}
    for intent, service in [('probe', adapter.SENSOR), ('parse', adapter.CSV), ('persist', loader)]:
        outputs = adapter.public.PORTS[service][1]
        links = {port: intent + '_' + port for port in outputs}
        for port, data_type in outputs.items():
            artifacts.append({'artifact_id': links[port], 'data_type': data_type, 'producer': intent,
                'consumers': ['persist'] if port == 'validated_data_object' and loader == adapter.TABULAR else [],
                'schema_ref': 'contracts/artifacts/' + SCHEMA_NAMES[port]})
        bindings.append({'intent_id': intent, 'service_id': service, 'service_version': '1.0.0', 'secret_bindings': [],
            'parameter_bindings': params[intent], 'input_bindings': [{'port': p, 'artifact_id': a} for p, a in ins[intent].items()],
            'output_bindings': [{'port': p, 'artifact_id': a} for p, a in links.items()]})
        intents.append({'intent_id': intent, 'inputs': list(ins[intent].values()), 'outputs': list(links.values())})
    ir = {'service_intents': intents, 'bindings': bindings, 'artifacts': artifacts,
        'control_flow': {'edges': [{'from': 'probe', 'to': 'parse'}, {'from': 'parse', 'to': 'persist'}],
            'gates': [{'gate_id': 'present', 'sensor_intent': 'probe', 'condition': 'probe_availability_decision.available == true', 'gated_intents': ['parse']}],
            'branches': [], 'parallel_groups': []},
        'runtime': {'target': 'argo-workflows', 'execution_profile': 'mock'},
        'policies': {'default_retries': 2, 'default_retry_delay_seconds': 60}, 'schedule': {'type': 'manual'}}
    return ir, intervention


def renamed(ir):
    """ID-only metamorphic test: no pipeline/model-specific dispatch."""
    result = copy.deepcopy(ir)
    intents = {i['intent_id']: 'renamed_' + i['intent_id'] for i in result['service_intents']}
    artifacts = {a['artifact_id']: 'renamed_' + a['artifact_id'] for a in result['artifacts']}
    for i in result['service_intents']:
        i['intent_id'] = intents[i['intent_id']]
        for direction in ('inputs', 'outputs'): i[direction] = [artifacts[a] for a in i[direction]]
    for b in result['bindings']:
        b['intent_id'] = intents[b['intent_id']]
        for direction in ('input_bindings', 'output_bindings'):
            for link in b[direction]: link['artifact_id'] = artifacts[link['artifact_id']]
    for a in result['artifacts']:
        a['artifact_id'] = artifacts[a['artifact_id']]
        if a['producer']: a['producer'] = intents[a['producer']]
        a['consumers'] = [intents[i] for i in a['consumers']]
    for e in result['control_flow']['edges']:
        e['from'], e['to'] = intents[e['from']], intents[e['to']]
    for g in result['control_flow']['gates']:
        g['sensor_intent'] = intents[g['sensor_intent']]
        g['gated_intents'] = [intents[i] for i in g['gated_intents']]
        aid, suffix = g['condition'].split('.', 1); g['condition'] = artifacts[aid] + '.' + suffix
    return result
