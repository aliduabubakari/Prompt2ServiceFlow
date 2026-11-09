"""Pure contract/oracle checks plus opt-in real PostgreSQL verification."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'audit/v2')); sys.path.insert(0, str(ROOT / 'audit'))
import run_v2_csv_postgres_controls as runner

ops, oracle, transport = runner.ops, runner.oracle, runner.transport
RAW = b'entity,amount,comment\nfirst,10,normal\nsecond,20,normal\n'


def contract(service=ops.TABULAR):
    return {'required_columns': ['entity', 'amount', 'comment'], 'loader_service': service, 'target_table': 'records'}


def resource(): return {'driver': ops.VERSION, 'engine': 'postgresql', 'database': 'p2sf_controls', 'schema': 'p2sf_control'}


class NoDatabase:
    def scalar(self, *args): pytest.fail('Rejected inputs must not access the target')
    def sql(self, *args): pytest.fail('Rejected inputs must not mutate the target')


def test_missing_file_uses_real_sensor_and_never_calls_database(tmp_path):
    result = ops.execute_control(NoDatabase(), resource(), tmp_path, None, contract())
    assert result['state'] == 'skipped_missing_input' and result['loader_called'] is False
    assert not (tmp_path / 'fixtures/source.csv').exists()
    assert json.loads((tmp_path / 'artifacts/availability_decision.json').read_text())['available'] is False


@pytest.mark.parametrize('raw', [b'entity,amount\nfirst,10\n', b'entity,amount,comment\nfirst,10,ok,extra\n', b'entity,amount,comment\n'])
def test_bad_csv_is_rejected_before_database(tmp_path, raw):
    with pytest.raises(ops.ContractError) as caught:
        ops.execute_control(NoDatabase(), resource(), tmp_path, raw, contract())
    assert caught.value.code == 'csv_validation_failed'


@pytest.mark.parametrize('name', ['a.b', 'x;DROP TABLE t', '../outside', '', 'x' * 64])
def test_unsupported_identifiers_cannot_enter_sql(name):
    with pytest.raises(ops.ContractError): ops.ident(name)


def test_unregistered_write_mode_is_not_silently_downgraded():
    dataset = ops.validated(RAW, contract()['required_columns'])['validated_dataset']
    with pytest.raises(ops.ContractError) as caught:
        ops.write_dataset(NoDatabase(), resource(), 'records', dataset, 'upsert')
    assert caught.value.code == 'unsupported_write_mode'


def test_dataset_receipt_must_match_actual_bound_bytes(tmp_path):
    artifact = tmp_path / 'dataset.json'; artifact.write_text('{}')
    metadata = {'contract_version': 'p2sf-tabular-object/1', 'dataset_ref': 'dataset.json', 'dataset_sha256': 'wrong'}
    with pytest.raises(ops.ContractError) as caught:
        ops.load_tabular(NoDatabase(), resource(), tmp_path, metadata, {'target_table': 'records', 'write_mode': 'append'})
    assert caught.value.code == 'dataset_hash_mismatch'
    metadata['dataset_ref'] = '../outside.json'
    with pytest.raises(ops.ContractError, match='escapes'):
        ops.load_tabular(NoDatabase(), resource(), tmp_path, metadata, {'target_table': 'records', 'write_mode': 'append'})


def test_mock_or_production_resource_cannot_be_reinterpreted():
    with pytest.raises(ops.ContractError): ops.check_resource({'driver': 'filesystem-mock', 'engine': 'postgresql'})
    value = resource(); value['host'] = 'production.example.invalid'
    with pytest.raises(ops.ContractError): ops.check_resource(value)


def test_valid_hash_cannot_override_explicit_failed_validation(tmp_path):
    import hashlib
    dataset = ops.validated(RAW, contract()['required_columns'])['validated_dataset']
    raw = ops.canonical_bytes(dataset); (tmp_path / 'dataset.json').write_bytes(raw)
    metadata = {'contract_version': 'p2sf-tabular-object/1', 'dataset_ref': 'dataset.json',
        'dataset_sha256': hashlib.sha256(raw).hexdigest(), 'success': False,
        'columns': dataset['columns'], 'row_count': 2, 'record_count': 2}
    with pytest.raises(ops.ContractError) as caught:
        ops.load_tabular(NoDatabase(), resource(), tmp_path, metadata, {'target_table': 'records', 'write_mode': 'append'})
    assert caught.value.code == 'dataset_metadata_mismatch'


@pytest.mark.parametrize('defect', ['empty', 'drop', 'value', 'schema', 'type'])
def test_oracle_does_not_accept_success_flag_without_matching_database_state(defect):
    snapshot = {'exists': True, 'columns': ['entity', 'amount', 'comment'], 'types': ['text'] * 3,
                'rows': [['first', '10', 'normal'], ['second', '20', 'normal']]}
    good = copy.deepcopy(snapshot)
    status = {'success': True, 'rows_written': 2}
    assert oracle.check_loaded(good, RAW, status)['pass']
    if defect == 'empty': snapshot['rows'] = []
    elif defect == 'drop': snapshot['rows'].pop()
    elif defect == 'value': snapshot['rows'][0][1] = '999'
    elif defect == 'schema': snapshot['columns'][0] = 'wrong'
    else: snapshot['types'][0] = 'integer'
    assert not oracle.check_loaded(snapshot, RAW, status)['pass']


def test_state_comparison_respects_unordered_database_rows():
    before = {'exists': True, 'columns': ['id'], 'types': ['text'], 'rows': [['a'], ['b'], ['b']]}
    after = {**before, 'rows': [['b'], ['a'], ['b']]}
    assert oracle.same_state(before, after)
    after['rows'].pop()
    assert not oracle.same_state(before, after)


@pytest.fixture(scope='module')
def database():
    image = os.environ.get('P2SF_POSTGRES_TEST_IMAGE')
    if not image: pytest.skip('Set P2SF_POSTGRES_TEST_IMAGE for real PostgreSQL verification')
    with transport.Postgres(transport.image_info(image)) as db: yield db


@pytest.mark.parametrize('service', [ops.SNAPSHOT, ops.TABULAR])
def test_actual_postgres_both_ports_append_replace_and_quoted_values(database, tmp_path, service):
    r = resource(); runner.reset(database, r)
    value = contract(service)
    raw = runner.variant(RAW, 'quoted_multiline')
    result = ops.execute_control(database, r, tmp_path / 'one', raw, value, mode='append')
    observed = oracle.observe(database, r['schema'], value['target_table'])
    assert oracle.check_loaded(observed, raw, result['load_status'])['pass']
    result = ops.execute_control(database, r, tmp_path / 'two', raw, value, mode='append')
    observed = oracle.observe(database, r['schema'], value['target_table'])
    assert oracle.check_loaded(observed, raw, result['load_status'], repetitions=2)['pass']
    second = runner.variant(raw, 'changed_value')
    result = ops.execute_control(database, r, tmp_path / 'three', second, value, mode='replace')
    observed = oracle.observe(database, r['schema'], value['target_table'])
    assert oracle.check_loaded(observed, second, result['load_status'])['pass']


def test_real_postgres_transaction_error_rolls_back_replacement(database, tmp_path):
    config = runner.replay.read_json(runner.CONFIG)
    item = {'raw': RAW, 'contract': contract()}
    result = runner.trial(database, item, 'transactional_rollback', tmp_path / 'trial', config)
    assert result['pass'], result
    recorded = json.loads((tmp_path / 'trial/result.json').read_text())
    assert recorded['failure']['sqlstate'] == '23514'
    assert json.loads((tmp_path / 'trial/before.json').read_text()) == json.loads((tmp_path / 'trial/after.json').read_text())
    assert 'CREATE TABLE' in (tmp_path / 'trial/target.sql').read_text()


def test_real_postgres_schema_mismatch_and_metadata_refusal(database, tmp_path):
    config = runner.replay.read_json(runner.CONFIG); item = {'raw': RAW, 'contract': contract()}
    for name in ['existing_schema_mismatch', 'metadata_hash_mismatch', 'missing_file', 'empty_allowed']:
        result = runner.trial(database, item, name, tmp_path / name, config)
        assert result['pass'], result


def test_real_postgres_mutants_are_detected_from_actual_target_state(database, tmp_path):
    config = runner.replay.read_json(runner.CONFIG); item = {'raw': RAW, 'contract': contract()}
    for name in config['mutants']:
        result = runner.mutant(database, item, name, tmp_path / name, config)
        assert result['detected'], result
        assert (tmp_path / name / 'target.sql').is_file()
