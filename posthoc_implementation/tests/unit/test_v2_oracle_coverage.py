"""Controls use the unchanged evaluator; synthetic claims are never model scores."""
import copy
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_oracle_coverage as pilot


def assertions():
    # A synthetic test oracle, with the same primitive predicate types. No
    # benchmark private assertion file is copied into a model context here.
    return {'scenarios': [{'scenario': 'nominal', 'assertions': [
        {'assertion_id': 'source_ok', 'type': 'json_path_equals', 'path': 'artifacts/first_status.json', 'json_path': 'success', 'expected': True},
        {'assertion_id': 'files', 'type': 'json_path_gte', 'path': 'artifacts/first_status.json', 'json_path': 'fixture.file_count', 'minimum': 1},
        {'assertion_id': 'records', 'type': 'json_path_gte', 'path': 'artifacts/first_status.json', 'json_path': 'fixture.record_count', 'minimum': 1},
        {'assertion_id': 'final_ok', 'type': 'json_path_equals', 'path': 'artifacts/last_status.json', 'json_path': 'success', 'expected': True},
        {'assertion_id': 'final_exists', 'type': 'file_exists', 'path': 'artifacts/last_status.json'},
        {'assertion_id': 'upstream', 'type': 'json_path_gte', 'path': 'artifacts/last_status.json', 'json_path': 'upstream_artifact_count', 'minimum': 1}]}]}


@pytest.mark.parametrize('condition', [
    'status_only_business_absent', 'status_with_empty_business_payload', 'status_with_unrelated_business_payload'])
def test_telemetry_only_predicates_do_not_inspect_business_artifact(condition, tmp_path):
    rows = assertions()['scenarios'][0]['assertions']
    files = pilot.witness(condition, 'first', 'last')
    result = pilot.evaluate_scenario(rows, files, tmp_path / condition)
    assert result['all_predicates_pass'] is True
    assert result['predicates_passed'] == 6
    assert result['workflow_executed'] is False
    assert result['model_performance_observation'] is False
    assert result['semantic_correctness'] == 'not_established'


@pytest.mark.parametrize('condition,expected', [
    ('source_record_count_zero', 5), ('final_success_false', 5),
    ('upstream_count_zero', 5), ('final_status_missing', 3)])
def test_status_mutations_are_detected_by_the_frozen_predicates(condition, expected, tmp_path):
    rows = assertions()['scenarios'][0]['assertions']
    result = pilot.evaluate_scenario(rows, pilot.witness(condition, 'first', 'last'), tmp_path / condition)
    assert result['all_predicates_pass'] is False
    assert result['predicates_passed'] == expected
    assert not any(row['status'] == 'error' for row in result['checks'])


def test_witnesses_do_not_adapt_to_changed_private_expected_values(tmp_path):
    oracle = assertions()
    oracle['scenarios'][0]['assertions'][0]['expected'] = False
    files = pilot.witness('status_only_business_absent', 'first', 'last')
    result = pilot.evaluate_scenario(oracle['scenarios'][0]['assertions'], files, tmp_path / 'counterexample')
    assert result['checks'][0]['status'] == 'fail'
    assert files['artifacts/first_status.json']['success'] is True


def test_an_actual_business_predicate_would_detect_missing_business_data(tmp_path):
    rows = assertions()['scenarios'][0]['assertions']
    rows.append({'assertion_id': 'business_file', 'type': 'file_exists', 'path': 'artifacts/last_artifact.json'})
    result = pilot.evaluate_scenario(rows, pilot.witness('status_only_business_absent', 'first', 'last'), tmp_path / 'business')
    assert result['predicates_passed'] == 6
    assert result['predicate_count'] == 7
    assert result['all_predicates_pass'] is False


@pytest.mark.parametrize('bad', ['', '../escape.json', '/tmp/escape.json', 'https://example.com/data', None])
def test_control_paths_cannot_escape_or_fetch_remote_content(bad, tmp_path):
    with pytest.raises(ValueError): pilot.contained(tmp_path, bad)


@pytest.mark.parametrize('mutation', ['empty', 'duplicate_scenario', 'duplicate_id', 'unsupported_type', 'path', 'scenario_name'])
def test_preflight_rejects_changed_or_unsafe_assertion_design(mutation):
    a = assertions()
    if mutation == 'empty': a['scenarios'][0]['assertions'] = []
    if mutation == 'duplicate_scenario': a['scenarios'].append(copy.deepcopy(a['scenarios'][0]))
    if mutation == 'duplicate_id': a['scenarios'][0]['assertions'].append(copy.deepcopy(a['scenarios'][0]['assertions'][0]))
    if mutation == 'unsupported_type': a['scenarios'][0]['assertions'][0]['type'] = 'json_schema'
    if mutation == 'path': a['scenarios'][0]['assertions'][0]['path'] = '../private.json'
    if mutation == 'scenario_name': a['scenarios'][0]['scenario'] = '../outside'
    with pytest.raises(ValueError): pilot.validate_assertions(a)


def test_witness_generation_is_fresh_and_has_no_expected_answer_dependency():
    first = pilot.witness('final_success_false', 'first', 'last')
    second = pilot.witness('status_only_business_absent', 'first', 'last')
    assert first['artifacts/last_status.json']['success'] is False
    assert second['artifacts/last_status.json']['success'] is True


def test_existing_control_directory_cannot_be_overwritten(tmp_path):
    with pytest.raises(FileExistsError):
        pilot.evaluate_scenario([], {}, tmp_path)


def test_dry_run_has_no_model_or_runtime_execution(monkeypatch, capsys):
    monkeypatch.setattr(pilot, 'prepare', lambda: ({'cases': ['main/unit'], 'conditions': ['one'], 'inventory_strata': {'main': 1}}, {}, None, {'x': 'sha'}))
    def forbidden(*args, **kwargs): raise AssertionError('No inference or workflow')
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    monkeypatch.setattr(pilot.subprocess, 'run', forbidden)
    assert pilot.main(['--dry-run']) == 0
    output = capsys.readouterr().out
    assert '"api_requests": 0' in output
    assert '"private_evidence_role": "evaluator_only"' in output


def test_inventory_keeps_telemetry_scope_separate_from_business_fields():
    source = assertions()
    row = pilot.predicate_inventory('main/unit', source)
    assert row['only_selected_status_telemetry_predicates'] is True
    source['scenarios'][0]['assertions'].append({
        'assertion_id': 'business', 'type': 'json_path_equals', 'path': 'artifacts/last_status.json',
        'json_path': 'output.total_revenue', 'expected': 123})
    changed = pilot.predicate_inventory('main/unit', source)
    assert changed['only_selected_status_telemetry_predicates'] is False
    assert changed['predicate_count'] == 7
    assert 'expected' not in changed['predicates'][-1]


def test_empty_predicate_inventory_is_not_vacuously_telemetry_only():
    row = pilot.predicate_inventory('main/unit', {'scenarios': []})
    assert row['only_selected_status_telemetry_predicates'] is False


def test_inventory_roster_requires_every_original_case(tmp_path):
    (tmp_path / 'cases/main/unit').mkdir(parents=True)
    assert pilot.inventory_roster(tmp_path, {'main': 1}) == ['main/unit']
    with pytest.raises(ValueError): pilot.inventory_roster(tmp_path, {'main': 2})
