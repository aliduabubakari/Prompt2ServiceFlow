"""Generic synthetic IR controls, with opt-in isolated real PostgreSQL tests."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'audit/v2')); sys.path.insert(0, str(ROOT / 'audit'))
import run_v2_csv_ir_adapter_controls as runner

adapter, factory = runner.adapter, runner.factory
RAW = b'entity,amount,comment\nfirst,10,normal\nsecond,20,normal\n'


def schemas():
    requirements = {
        'availability_decision': {'available': 'boolean'}, 'check_status': {'success': 'boolean'},
        'validated_dataset': {'columns': 'array', 'rows': 'array'},
        'validated_data_object': {'source_uri': 'string', 'record_count': 'integer', 'columns': 'array'},
        'validation_status': {'success': 'boolean', 'rows_read': 'integer'},
        'target_database_reference': {'target_table': 'string', 'rows_imported': 'integer'},
        'load_status': {'success': 'boolean', 'rows_loaded': 'integer'}}
    return {'contracts/artifacts/' + factory.SCHEMA_NAMES[port]:
        {'type': 'object', 'required': list(fields), 'properties': {k: {'type': t} for k, t in fields.items()}}
        for port, fields in requirements.items()}


def control(tmp_path, service=adapter.SNAPSHOT, **kwargs):
    ir, intervention = factory.authored(RAW, service, tmp_path / 'fixtures', **kwargs)
    return ir, intervention, schemas()


class NoDatabase:
    def sql(self, *args): pytest.fail('Refused or gated execution must not mutate the database')
    def scalar(self, *args): pytest.fail('Refused or gated execution must not access the database')


@pytest.mark.parametrize('missing', [True, False])
def test_real_sensor_gate_and_transitive_skip(tmp_path, missing):
    ir, intervention, schema_set = control(tmp_path, missing=missing)
    if not missing: runner.parameters(ir, adapter.SENSOR)['filename_pattern'] = 'absent_*.csv'
    source = copy.deepcopy(ir)
    plan = adapter.compile_projection(ir, intervention, schema_set)
    result = adapter.execute(plan, NoDatabase(), tmp_path / 'fixtures', tmp_path / 'run')
    assert result['state'] == 'skipped_missing_input' and result['loader_called'] is False
    assert [e['state'] for e in result['events']] == ['completed', 'skipped_dependency_or_gate', 'skipped_dependency_or_gate']
    assert ir == source and plan['source_ir'] == source and result['source_ir_unchanged']


@pytest.mark.parametrize('defect,code', [
    ('binding', 'missing_fixture_link'), ('columns', 'missing_required_columns'), ('upsert', 'unsupported_write_mode'),
    ('dependency', 'unsupported_dependency'), ('consumer', 'consumer_mismatch'), ('type', 'port_type_mismatch'),
    ('gate', 'unsupported_gate'), ('duplicate', 'duplicate_identity'), ('producer', 'writer_mismatch'),
    ('template', 'unresolved_parameters'), ('recursive', 'unsupported_sensor'), ('sftp', 'unsupported_sensor'),
    ('glob', 'unsupported_glob'), ('secret', 'unsupported_binding'), ('schema', 'nonlocal_schema')])
def test_no_binding_parameter_graph_or_key_completion(tmp_path, defect, code):
    ir, intervention, schema_set = control(tmp_path)
    if defect == 'binding': ir['artifacts'][0].pop('fixture_ref')
    elif defect == 'columns': runner.parameters(ir, adapter.CSV).pop('required_columns')
    elif defect == 'upsert': runner.parameters(ir, adapter.SNAPSHOT)['load_mode'] = 'upsert'
    elif defect == 'dependency': ir['control_flow']['edges'].pop()
    elif defect == 'consumer': ir['artifacts'][0]['consumers'] = []
    elif defect == 'type': ir['artifacts'][0]['data_type'] = 'object'
    elif defect == 'gate': ir['control_flow']['gates'][0]['condition'] = '__import__("os")'
    elif defect == 'duplicate': ir['artifacts'].append(copy.deepcopy(ir['artifacts'][0]))
    elif defect == 'producer': next(a for a in ir['artifacts'] if a['artifact_id'] == 'parse_validated_dataset')['producer'] = 'persist'
    elif defect == 'template': runner.parameters(ir, adapter.CSV)['output_path'] = '/data/{{ ds }}/f.json'
    elif defect == 'recursive': runner.parameters(ir, adapter.SENSOR)['recursive'] = True
    elif defect == 'sftp': runner.parameters(ir, adapter.SENSOR)['location_type'] = 'sftp'
    elif defect == 'glob': runner.parameters(ir, adapter.SENSOR)['filename_pattern'] = '../*.csv'
    elif defect == 'secret': ir['bindings'][0]['secret_bindings'] = ['secret']
    elif defect == 'schema': next(iter(schema_set.values()))['$ref'] = 'https://example.invalid/schema'
    with pytest.raises(adapter.Error) as caught: adapter.compile_projection(ir, intervention, schema_set)
    assert caught.value.code == code


@pytest.mark.parametrize('label', ['a.b.c', 'public.x;DROP TABLE x', 'bad-name.x', '../x', 'public.' + 'x' * 64])
def test_qualified_names_cannot_supply_sql(label):
    with pytest.raises(adapter.Error): adapter.target_name(label, 'p2sf_adapter')


def test_explicit_qualified_names_and_path_namespace():
    assert adapter.target_name('public.transactions', 'other') == ('public', 'transactions')
    assert adapter.target_name('transactions', 'other') == ('other', 'transactions')
    assert adapter.kernels.logical_path('/reports/x.json') != adapter.kernels.logical_path('reports/x.json')


def test_source_and_plan_mutations_are_detected(tmp_path):
    ir, intervention, schema_set = control(tmp_path)
    plan = adapter.compile_projection(ir, intervention, schema_set)
    plan['nodes']['persist']['parameters']['load_mode'] = 'append'
    with pytest.raises(adapter.Error) as caught: adapter.execute(plan, NoDatabase(), tmp_path / 'fixtures', tmp_path / 'run')
    assert caught.value.code == 'changed_plan'


def test_resource_and_csv_bytes_are_checked_before_execution(tmp_path):
    ir, intervention, schema_set = control(tmp_path)
    (tmp_path / 'fixtures/location.json').write_text('{"changed":true}')
    plan = adapter.compile_projection(ir, intervention, schema_set)
    with pytest.raises(adapter.Error) as caught: adapter.execute(plan, NoDatabase(), tmp_path / 'fixtures', tmp_path / 'run')
    assert caught.value.code == 'fixture_hash_mismatch'


def test_missing_mounted_file_must_be_an_explicit_intervention(tmp_path):
    ir, intervention, schema_set = control(tmp_path)
    (tmp_path / 'fixtures/payload.csv').unlink()
    plan = adapter.compile_projection(ir, intervention, schema_set)
    with pytest.raises(adapter.Error) as caught: adapter.execute(plan, NoDatabase(), tmp_path / 'fixtures', tmp_path / 'run')
    assert caught.value.code == 'fixture_hash_mismatch'


def test_renaming_keeps_gate_inputs_and_outputs_consistent(tmp_path):
    ir, intervention, schema_set = control(tmp_path, missing=True)
    renamed = factory.renamed(ir)
    plan = adapter.compile_projection(renamed, intervention, schema_set)
    result = adapter.execute(plan, NoDatabase(), tmp_path / 'fixtures', tmp_path / 'run')
    assert result['events'][-1]['intent'] == 'renamed_persist'
    assert result['loader_called'] is False


@pytest.fixture(scope='module')
def database():
    image = os.environ.get('P2SF_POSTGRES_TEST_IMAGE')
    if not image: pytest.skip('Set P2SF_POSTGRES_TEST_IMAGE for isolated actual PostgreSQL tests')
    with runner.transport.Postgres(runner.transport.image_info(image)) as db: yield db


@pytest.mark.parametrize('service', [adapter.SNAPSHOT, adapter.TABULAR])
@pytest.mark.parametrize('scenario', json.loads(runner.CONFIG.read_text())['positives'] +
                         json.loads(runner.CONFIG.read_text())['gates'] + json.loads(runner.CONFIG.read_text())['refusals'])
def test_real_database_identity_ports_counts_receipts_and_rollback(database, tmp_path, service, scenario):
    case = {'raw': RAW, 'loader_service': service}
    config = json.loads(runner.CONFIG.read_text())
    result = runner.trial(database, case, scenario, tmp_path / 'control', schemas(), config)
    assert result['pass'], result
    if scenario in config['positives']:
        receipt = result['receipt']; root = tmp_path / 'control' / ('repeat' if scenario == 'repeat_append' else 'execution')
        metadata = json.loads(next((root / 'artifacts').glob('*validated_data_object.json')).read_text())
        dataset = root / metadata['dataset_ref']
        assert dataset.is_file() and runner.controls.sha256(dataset) == metadata['dataset_sha256']
        assert receipt['load_status']['rows_loaded'] == 2
        assert receipt['not_executed']['policies']['default_retries'] == 2
        if service == adapter.SNAPSHOT:
            reference = json.loads(next((root / 'artifacts').glob('*_target_database_reference.json')).read_text())
            assert reference['target_table'] == ('p2sf_other' if scenario == 'other_schema' else 'p2sf_adapter') + '.records_generic'
            assert reference['rows_imported'] == 2


@pytest.mark.parametrize('defect', ['fake_success_empty_target', 'corrupt_value', 'drop_row', 'wrong_schema', 'wrong_status', 'gate_bypass'])
def test_independent_oracle_detects_real_database_and_status_mutants(database, tmp_path, defect):
    result = runner.mutant(database, {'raw': RAW, 'loader_service': adapter.TABULAR}, defect, tmp_path / 'mutant', schemas())
    assert result['detected'], result
