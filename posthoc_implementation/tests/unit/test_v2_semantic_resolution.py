"""Typed completion and real business outputs, using synthetic public inputs.

No model calls, reference compositions, private assertions, or recorded model
execution are needed by these tests.
"""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_resolution as runner

completion = runner.semantic_completion
backend = runner.pilot.integration.backend


def contract():
    return runner.replay.read_json(ROOT / 'audit/v2/runtime_profiles/output-projections-v1.json')


def policy():
    return runner.replay.read_json(ROOT / 'audit/v2/assembly_policy.json')


def catalog_get(service, version):
    if service not in backend.window.OPERATIONS or version != '1.0.0':
        return None, 'unregistered'
    return {'interface': {
        'inputs': [{'name': 'input_artifacts', 'channel': 'artifact', 'data_type': 'any', 'cardinality': 'many'}],
        'outputs': [
            {'name': 'output_artifacts', 'channel': 'artifact', 'data_type': 'any', 'cardinality': 'many', 'required': True},
            {'name': 'execution_report', 'channel': 'artifact', 'data_type': 'status', 'cardinality': 'one', 'required': True}]}}, None


def synthetic_ir(prefix='arbitrary'):
    """Six operations with independent identifiers and one omitted report link."""
    stages = list(backend.window.OPERATIONS.items())
    intents = [prefix + '_step_' + str(i) for i in range(6)]
    data = [prefix + '_bundle_' + str(i) for i in range(7)]
    status = [prefix + '_status_' + str(i) for i in range(6)]
    report = prefix + '_report'
    artifacts = []
    for i, identity in enumerate(data):
        artifacts.append({'artifact_id': identity, 'kind': 'artifact', 'data_type': 'json',
            'role': 'input' if i == 0 else 'output' if i == 6 else 'intermediate',
            'producer': None if i == 0 else intents[i - 1],
            'consumers': [intents[i]] if i < 6 else [],
            **({'fixture_ref': 'fixtures/inputs/fixture.json'} if i == 0 else {})})
    artifacts.extend({'artifact_id': identity, 'kind': 'artifact', 'data_type': 'status',
                      'role': 'status', 'producer': intents[i], 'consumers': []}
                     for i, identity in enumerate(status))
    artifacts.append({'artifact_id': report, 'kind': 'artifact', 'data_type': 'json',
                      'role': 'report', 'producer': intents[-1], 'consumers': []})
    services, bindings = [], []
    for i, (service, (label, _)) in enumerate(stages):
        services.append({'intent_id': intents[i], 'inputs': [data[i]],
                         'outputs': [data[i + 1], status[i]] + ([report] if i == 5 else []),
                         'description': 'Synthetic public service choice.'})
        bindings.append({'intent_id': intents[i], 'service_id': service, 'service_version': '1.0.0',
                         'parameter_bindings': {'operation_profile': label},
                         'input_bindings': [{'port': 'input_artifacts', 'artifact_id': data[i]}],
                         'output_bindings': [{'port': 'output_artifacts', 'artifact_id': data[i + 1]},
                                             {'port': 'execution_report', 'artifact_id': status[i]}]})
    return {'composition_id': prefix, 'artifacts': artifacts, 'service_intents': services, 'bindings': bindings,
            'control_flow': {'edges': [{'from': a, 'to': b} for a, b in zip(intents, intents[1:])]},
            'runtime': {'execution_profile': 'reference'}}


def complete(value, get=catalog_get):
    return completion.complete(value, get, contract(), policy())


@pytest.mark.parametrize('prefix', ['arbitrary', 'renamed_every_identity'])
def test_completion_uses_public_types_and_declarations_not_names(prefix):
    original = synthetic_ir(prefix)
    old = copy.deepcopy(original)
    value, decision = complete(original)
    assert original == old
    assert decision['state'] == 'completed'
    assert len(decision['operations']) == 1
    assert decision['operations'][0]['rule'] == 'complete_declared_registered_auxiliary_projection'
    assert value['bindings'][-1]['output_bindings'][-1] == {
        'port': 'output_artifacts', 'artifact_id': prefix + '_report'}
    completion.verify_protected(old, value, decision['operations'])
    profile = runner.replay.read_json(ROOT / 'audit/v2/runtime_profiles/bounded-window-1.json')
    assert backend.compile_plan(value, profile)['mock_fallback'] is False
    repeated, again = complete(value)
    assert repeated == value and again['state'] == 'unchanged' and again['operations'] == []


@pytest.mark.parametrize('mutation', ['consumed', 'input_read', 'wrong_type', 'external_source',
    'not_declared_by_intent', 'two_reports', 'two_primary', 'wrong_label', 'undeclared_input', 'duplicate_writer'])
def test_ambiguous_or_unsupported_completion_is_transactional(mutation):
    value = synthetic_ir()
    report, publisher = value['artifacts'][-1], value['bindings'][-1]
    if mutation == 'consumed': report['consumers'] = [value['service_intents'][0]['intent_id']]
    if mutation == 'input_read': value['service_intents'][0]['inputs'].append(report['artifact_id'])
    if mutation == 'wrong_type': report['data_type'] = 'table'
    if mutation == 'external_source': report['fixture_ref'] = 'fixtures/inputs/report.json'
    if mutation == 'not_declared_by_intent': value['service_intents'][-1]['outputs'].remove(report['artifact_id'])
    if mutation == 'two_reports':
        other = {**report, 'artifact_id': 'another_report'}
        value['artifacts'].append(other)
        value['service_intents'][-1]['outputs'].append(other['artifact_id'])
    if mutation == 'two_primary': publisher['output_bindings'].append(copy.deepcopy(publisher['output_bindings'][0]))
    if mutation == 'wrong_label': publisher['parameter_bindings']['operation_profile'] = 'invented_operation'
    if mutation == 'undeclared_input': value['bindings'][0]['input_bindings'][0]['artifact_id'] = 'absent'
    if mutation == 'duplicate_writer': value['bindings'][0]['output_bindings'].append(copy.deepcopy(publisher['output_bindings'][0]))
    original = copy.deepcopy(value)
    fixed, decision = complete(value)
    assert value == fixed == original
    assert decision['state'] == 'blocked_no_changes' and decision['operations'] == []


@pytest.mark.parametrize('field,value', [('cardinality', 'one'), ('channel', 'parameter'), ('data_type', 'table')])
def test_descriptor_must_support_real_projection(field, value):
    def wrong(service, version):
        descriptor, error = catalog_get(service, version)
        descriptor['interface']['outputs'][0][field] = value
        return descriptor, error
    original = synthetic_ir()
    fixed, decision = complete(original, wrong)
    assert fixed == original and decision['state'] == 'blocked_no_changes'


def test_unknown_projection_is_never_accepted():
    c = contract()
    c['rules'][0]['projection'] = 'fill_expected_answer'
    with pytest.raises(ValueError):
        completion.complete(synthetic_ir(), catalog_get, c, policy())


def test_synthetic_execution_computes_metrics_csv_and_auxiliary_report(tmp_path):
    value, _ = complete(synthetic_ir('another_task'))
    profile = runner.replay.read_json(ROOT / 'audit/v2/runtime_profiles/bounded-window-1.json')
    fixtures = tmp_path / 'public_inputs'
    fixtures.mkdir()
    (fixtures / 'fixture.json').write_text(json.dumps({'inputs': {'readings': 'readings.jsonl', 'buildings': 'registry.csv'},
        'batch_window_start': '2026-01-01T00:00:00Z', 'batch_window_end': '2026-01-01T01:00:00Z',
        'window_size_minutes': 30, 'demand_threshold_pct': 85, 'power_factor_min': .85}))
    rows = [{'meter_id': 'meter', 'building_id': 'building', 'timestamp': time,
             'energy_kwh': energy, 'demand_kw': demand, 'power_factor': quality}
            for time, energy, demand, quality in [('2026-01-01T00:00:00Z', 2.5, 40, .9),
                ('2026-01-01T00:15:00Z', 3.5, 85, .8), ('2026-01-01T00:30:00Z', 4, 30, .95)]]
    (fixtures / 'readings.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    (fixtures / 'registry.csv').write_text('building_id,demand_limit_kw\nbuilding,100\n')
    destination = tmp_path / 'execution'
    trace = backend.execute(value, profile, destination, fixtures)
    assert trace['workflow_status'] == 'completed'
    raw = {'scenario': 'nominal', '_errors': [], '_snapshot': {
        p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob('*') if p.is_file()}}
    checked = runner.pilot.integration.prior.neutral_check(raw, value, fixtures, profile)
    assert checked['pass'], checked
    payload = json.loads((destination / 'artifacts/another_task_bundle_6.json').read_text())
    report = json.loads((destination / 'artifacts/another_task_report.json').read_text())
    assert [row['energy_kwh_sum'] for row in payload['metrics']] == [6, 4]
    assert payload['metrics'][0]['high_demand'] is True
    assert report == json.loads((destination / payload['published_files']['audit']).read_text())
    assert 'metrics' not in report and report != payload
    assert trace['semantic_backend']['mock_fallback'] is False
    for defect in ('wrong_energy', 'wrong_alert', 'constant_summary', 'missing_publication'):
        corrupted = runner.pilot.integration.prior.mutate(raw, value, defect)
        assert not runner.pilot.integration.prior.neutral_check(corrupted, value, fixtures, profile)['pass']


def test_dry_run_has_no_model_or_execution_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(runner, 'prepare', lambda: (
        {}, {'model_id': 'saved', 'design': {'case': 'public'}}, {}, {},
        {'state': 'completed', 'operations': [{}]}, {'state': 'ready'}, {}, None, {}, None, {}))
    def forbidden(*args, **kwargs): raise AssertionError('No inference or execution in preflight')
    monkeypatch.setattr(runner.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(runner.controls, '_execute_scenarios', forbidden)
    assert runner.main(['--dry-run']) == 0
    assert '"api_requests": 0' in capsys.readouterr().out
