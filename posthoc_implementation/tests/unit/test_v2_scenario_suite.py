"""Authored scenario/receipt controls. No original saved-IR execution."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'audit/v2'), str(ROOT / 'audit')]
import scenario_suite as suite
import scenario_suite_controls as authored


def schemas():
    props = {'availability_decision': {'available': 'boolean'}, 'check_status': {'success': 'boolean'},
        'validated_dataset': {'columns': 'array', 'rows': 'array'}, 'validated_data_object': {'source_uri': 'string', 'record_count': 'integer', 'columns': 'array'},
        'validation_status': {'success': 'boolean', 'rows_read': 'integer'}, 'target_database_reference': {'target_table': 'string', 'rows_imported': 'integer'},
        'load_status': {'success': 'boolean', 'rows_loaded': 'integer'}}
    return {'contracts/artifacts/' + authored.authored.SCHEMA_NAMES[port]:
        {'type': 'object', 'required': list(fields), 'properties': {k: {'type': t} for k, t in fields.items()}} for port, fields in props.items()}


def control(tmp_path): return authored.make_control(tmp_path / 'authored', suite.adapter.SNAPSHOT, schemas())


@pytest.mark.parametrize('index', [0, 1, 2])
def test_selected_parameter_changes_bound_bytes_not_the_composition(tmp_path, index):
    row, specs, predicates = control(tmp_path); expected = specs[index]; original = copy.deepcopy(row['plan'])
    plan, receipt = suite.materialize(row, expected, tmp_path / 'supplied')
    assert plan['source_ir'] == original['source_ir'] and row['plan'] == original
    assert plan['schemas'] == original['schemas'] and plan['source_ir_sha256'] == original['source_ir_sha256']
    assert plan['intervention']['scenario_input']['parameters'] == expected['parameters']
    path = tmp_path / 'supplied' / receipt['csv_paths'][0]
    if index == 1: assert not path.exists() and receipt['selected_sha256'] == 'MISSING'
    else: assert path.read_bytes() == Path(expected['selected_path']).read_bytes()
    for ref, entry in plan['intervention']['fixtures'].items():
        if entry['kind'] != 'csv': assert (tmp_path / 'supplied' / entry['path']).read_bytes() == Path(row['fixture_sources'][ref]).read_bytes()


@pytest.mark.parametrize('name,params', [('bad/name', {'selected-file': 'batch_17.csv'}), ('safe', {}),
    ('safe', {'selected-file': '../escape'}), ('safe', {'selected-file': '{{ date }}.csv'}),
    ('safe', {'selected-file': '*.csv'}), ('safe', {'selected-file': 'batch_17.csv', 'unused': True})])
def test_scenarios_do_not_guess_parameters_or_ignore_unknown_inputs(tmp_path, name, params):
    row, specs, _ = control(tmp_path)
    with pytest.raises(ValueError): suite.spec(row, {'name': name, 'parameters': params}, specs[0]['fixture_root'], 'selected-file')


@pytest.mark.parametrize('change', ['spec', 'fixture', 'source_plan', 'resource', 'source_graph'])
def test_source_and_input_changes_are_rejected(tmp_path, change):
    row, specs, _ = control(tmp_path); value = copy.deepcopy(specs[0])
    if change == 'spec': value['selected_filename'] = 'other.csv'
    elif change == 'fixture': Path(value['selected_path']).write_bytes(b'changed')
    elif change == 'source_plan': row['plan']['plan_sha256'] = 'changed'
    elif change == 'source_graph': row['plan']['source_ir']['control_flow']['gates'] = []
    else:
        ref = next(r for r, e in row['plan']['intervention']['fixtures'].items() if e['kind'] == 'database')
        Path(row['fixture_sources'][ref]).write_text('{"changed":true}')
    with pytest.raises(ValueError): suite.materialize(row, value, tmp_path / 'supplied')


def result(value, passed=True):
    return {'scenario_id': value['scenario_id'], 'spec_sha256': value['spec_sha256'], 'snapshot_verified': True,
            'pass': passed, 'assertions': [{'pass': True}], 'business_checks': {'actual_database': True}}


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'unknown', 'wrong_spec', 'unchecked', 'unverified', 'failed'])
def test_complete_suite_requires_every_scenario_exactly_once_with_evidence(tmp_path, defect):
    row, specs, _ = control(tmp_path); results = [result(s) for s in specs]
    assert suite.aggregate(specs, results)['suite_pass']
    if defect == 'missing': results.pop()
    elif defect == 'duplicate': results.append(copy.deepcopy(results[0]))
    elif defect == 'unknown': results[0]['scenario_id'] = 'different'
    elif defect == 'wrong_spec': results[0]['spec_sha256'] = 'wrong'
    elif defect == 'unchecked': results[0]['assertions'] = []
    elif defect == 'unverified': results[0]['snapshot_verified'] = False
    else: results[0]['pass'] = False
    assert not suite.aggregate(specs, results)['suite_pass']


@pytest.mark.parametrize('definitions', [[], [{'assertion_id': 'x', 'type': 'shell', 'path': 'artifacts/a.json'}],
    [{'assertion_id': 'x', 'type': 'file_exists', 'path': '../outside'}],
    [{'assertion_id': 'x', 'type': 'json_path_equals', 'path': 'artifacts/a.json', 'json_path': '__import__("os")', 'expected': True}]])
def test_predicates_are_nonempty_closed_and_path_bounded(definitions):
    with pytest.raises(ValueError): suite.validate_assertions(definitions)


def test_predicate_compares_json_boolean_and_integer_without_coercion(tmp_path):
    suite.write(tmp_path / 'artifacts/status.json', {'available': 1})
    assert not suite.predicate({'type': 'json_path_equals', 'path': 'artifacts/status.json', 'json_path': 'available', 'expected': True}, tmp_path)


def test_missing_or_unsealed_snapshot_cannot_satisfy_file_absence(tmp_path):
    row, specs, predicates = control(tmp_path)
    checked = suite.score(tmp_path / 'no_execution', specs[1], predicates[specs[1]['scenario_id']])
    assert not checked['pass'] and not checked['snapshot_verified'] and checked['assertions'] == []


def test_input_builder_does_not_consume_private_predicate_expected_values(tmp_path):
    row, specs, predicates = control(tmp_path); prior = copy.deepcopy(specs)
    for definitions in predicates.values():
        for d in definitions:
            if 'expected' in d: d['expected'] = 'arbitrary unrelated expected value'
    assert specs == prior
    suite.materialize(row, specs[0], tmp_path / 'inputs')
    assert row['plan']['source_ir_sha256'] == specs[0]['source_ir_sha256']


@pytest.mark.parametrize('service', [suite.adapter.SNAPSHOT, suite.adapter.TABULAR])
def test_actual_postgres_authored_scenario_loop_snapshots_and_all_mutants(tmp_path, service):
    image = os.environ.get('P2SF_POSTGRES_TEST_IMAGE')
    if not image: pytest.skip('Set P2SF_POSTGRES_TEST_IMAGE for isolated authored PostgreSQL scenario controls')
    root = tmp_path / 'control'
    checked = authored.run(root, service, schemas(), suite.transport.image_info(image))
    assert checked['required_scenarios'] == checked['recorded_scenarios'] == checked['passed_scenarios'] == 3
    assert checked['control_gate_pass'] and all(checked['mutants'].values()) and set(checked['mutants']) == set(authored.MUTANTS)
    specs = suite.read(root / 'authored_specs.json'); predicates = suite.read(root / 'authored_predicates.json')
    for value in specs:
        directory = root / 'executions' / value['scenario_id']
        snapshot, provenance, receipt = suite.verify_snapshot(directory, value)
        assert provenance['state'] == 'completed'
        result_again = suite.score(directory, value, predicates[value['scenario_id']]); assert result_again['pass']
        if value['selected_sha256'] == 'MISSING':
            assert not suite.read(snapshot / 'database/after.json')['exists']
            assert provenance['adapter_receipt']['loader_called'] is False
        else:
            before, after = suite.read(snapshot / 'database/before.json'), suite.read(snapshot / 'database/after.json')
            assert not before['exists'] and len(after['rows']) == (2 if value['scenario_id'] == 'present_case' else 3)
        # Assertions are read from sealed output files: subsequent modification
        # must fail instead of silently producing a different semantic score.
        path = next((snapshot / 'artifacts').glob('*availability_decision.json')); path.write_text('{}')
        assert not suite.score(directory, value, predicates[value['scenario_id']])['snapshot_verified']


def test_failed_execution_is_retained_but_cannot_pass_absence_checks(tmp_path):
    image = os.environ.get('P2SF_POSTGRES_TEST_IMAGE')
    if not image: pytest.skip('Set P2SF_POSTGRES_TEST_IMAGE for authored failed-execution verification')
    bad = schemas(); bad['contracts/artifacts/availability_decision.schema.json']['properties']['available']['type'] = 'integer'
    row, specs, predicates = authored.make_control(tmp_path / 'authored_failed', suite.adapter.SNAPSHOT, bad)
    expected = specs[1]
    directory = tmp_path / 'failed_execution'
    suite.execute(row, expected, directory, suite.transport.image_info(image))
    snapshot, provenance, receipt = suite.verify_snapshot(directory, expected)
    assert provenance['state'] == 'failed' and provenance['execution_error']['code'] == 'output_schema_mismatch'
    result = suite.score(directory, expected, predicates[expected['scenario_id']])
    assert result['snapshot_verified'] and not result['pass']
    assert not any(r['pass'] for r in result['assertions'])
