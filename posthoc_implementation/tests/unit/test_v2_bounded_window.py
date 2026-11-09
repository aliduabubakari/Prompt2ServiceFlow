"""Public-rule tests; no private assertions, scores, or native gold programs."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_bounded_window as runner


def profile():
    return runner.replay.read_json(runner.CONFIG)


def ir():
    artifacts = [{'artifact_id': 'source', 'producer': None, 'fixture_ref': 'fixtures/inputs/fixture.json', 'data_type': 'any'}]
    bindings, intents, edges = [], [], []
    previous = 'source'
    for index, (service, (label, _)) in enumerate(runner.engine.OPERATIONS.items()):
        intent, output, status = f'stage_{index}', f'payload_{index}', f'status_{index}'
        intents.append({'intent_id': intent})
        artifacts.extend([{'artifact_id': output, 'producer': intent, 'data_type': 'any'},
                          {'artifact_id': status, 'producer': intent, 'data_type': 'status'}])
        bindings.append({'intent_id': intent, 'service_id': service, 'service_version': '1.0.0',
            'input_bindings': [{'port': 'input_artifacts', 'artifact_id': previous}],
            'output_bindings': [{'port': 'output_artifacts', 'artifact_id': output}, {'port': 'execution_report', 'artifact_id': status}],
            'parameter_bindings': {'operation_profile': label, 'modality_policy': {'true_streaming': False}}})
        if index:
            edges.append({'from': f'stage_{index-1}', 'to': intent})
        previous = output
    return {'artifacts': artifacts, 'bindings': bindings, 'service_intents': intents,
            'control_flow': {'edges': edges, 'branches': [], 'gates': [], 'parallel_groups': []}}


def inputs(tmp_path, records=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = {'inputs': {'readings': 'readings.jsonl', 'buildings': 'buildings.csv'},
        'batch_window_start': '2026-01-01T00:00:00Z', 'batch_window_end': '2026-01-01T01:00:00Z',
        'window_size_minutes': 30, 'demand_threshold_pct': 85, 'power_factor_min': 0.85}
    rows = records if records is not None else [
        {'meter_id': 'm1', 'building_id': 'b1', 'timestamp': '2026-01-01T00:00:00Z', 'energy_kwh': 2.5, 'demand_kw': 40, 'power_factor': 0.9},
        {'meter_id': 'm1', 'building_id': 'b1', 'timestamp': '2026-01-01T00:15:00Z', 'energy_kwh': 3.5, 'demand_kw': 85, 'power_factor': 0.8},
        {'meter_id': 'm1', 'building_id': 'b1', 'timestamp': '2026-01-01T00:30:00Z', 'energy_kwh': 4, 'demand_kw': 30, 'power_factor': 0.95}]
    (tmp_path / 'fixture.json').write_text(json.dumps(config))
    (tmp_path / 'readings.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (tmp_path / 'buildings.csv').write_text('building_id,demand_limit_kw\nb1,100\n')
    return tmp_path


def execute(tmp_path, fixture_root):
    workspace = tmp_path / 'workspace'
    trace = runner.engine.execute(ir(), profile(), workspace, fixture_root)
    snapshot = {p.relative_to(workspace).as_posix(): p.read_bytes() for p in workspace.rglob('*') if p.is_file()}
    return trace, {'_snapshot': snapshot, '_errors': [] if trace['workflow_status'] == 'completed' else ['workflow rejected']}


def test_real_chain_matches_independent_oracle_and_known_arithmetic(tmp_path):
    fixture = inputs(tmp_path / 'inputs')
    trace, result = execute(tmp_path, fixture)
    assert all(s == 'executed' for s in trace['states'].values())
    assert runner.oracle.check(result, ir(), fixture, profile(), 'nominal')['pass']
    value = json.loads(result['_snapshot']['artifacts/payload_5.json'])
    assert value['metrics'][0]['energy_kwh_sum'] == 6
    assert value['metrics'][0]['high_demand'] is True  # inclusive 85 percent
    assert value['metrics'][0]['low_power_factor'] is False  # equality at 0.85


def test_exact_duplicates_removed_and_conflicts_rejected(tmp_path):
    fixture = inputs(tmp_path / 'input')
    data = [json.loads(s) for s in (fixture / 'readings.jsonl').read_text().splitlines()]
    data.append(copy.deepcopy(data[0])); inputs(fixture, data)
    _, result = execute(tmp_path / 'first', fixture)
    assert runner.oracle.check(result, ir(), fixture, profile(), 'duplicate')['pass']
    data[-1]['energy_kwh'] += 1; inputs(fixture, data)
    trace, result = execute(tmp_path / 'second', fixture)
    assert trace['states']['stage_2'] == 'failed' and trace['states']['stage_5'] == 'skipped'
    assert runner.oracle.check(result, ir(), fixture, profile(), 'conflicting_duplicate')['pass']


def test_shuffling_invariance(tmp_path):
    fixture = inputs(tmp_path / 'inputs')
    _, first = execute(tmp_path / 'a', fixture)
    path = fixture / 'readings.jsonl'; path.write_text('\n'.join(reversed(path.read_text().splitlines())) + '\n')
    _, second = execute(tmp_path / 'b', fixture)
    a, b = (json.loads(r['_snapshot']['artifacts/payload_5.json']) for r in (first, second))
    assert a['metrics'] == b['metrics']


def test_quality_threshold_equality_not_changed_by_float_roundoff(tmp_path):
    fixture = inputs(tmp_path / 'inputs')
    data = [json.loads(s) for s in (fixture / 'readings.jsonl').read_text().splitlines()]
    for row, quality in zip(data, [0.1, 0.2, 0.3]):
        row['power_factor'] = quality; row['timestamp'] = '2026-01-01T00:00:00Z'; row['meter_id'] += str(quality)
    inputs(fixture, data)
    config = runner.replay.read_json(fixture / 'fixture.json'); config['power_factor_min'] = 0.2
    runner.controls.write_json(fixture / 'fixture.json', config)
    _, result = execute(tmp_path, fixture)
    metrics = json.loads(result['_snapshot']['artifacts/payload_5.json'])['metrics']
    assert metrics[0]['low_power_factor'] is False
    assert runner.oracle.check(result, ir(), fixture, profile(), 'nominal')['pass']


def test_boundaries_same_timestamp_meter_sum_and_no_empty_windows(tmp_path):
    fixture = inputs(tmp_path / 'inputs')
    data = [json.loads(s) for s in (fixture / 'readings.jsonl').read_text().splitlines()]
    extra = copy.deepcopy(data[0]); extra['meter_id'] = 'm2'; extra['demand_kw'] = 60; data.append(extra)
    outside = copy.deepcopy(extra); outside['meter_id'] = 'm3'; outside['timestamp'] = '2026-01-01T01:00:00Z'; data.append(outside)
    inputs(fixture, data)
    _, result = execute(tmp_path, fixture)
    value = json.loads(result['_snapshot']['artifacts/payload_5.json'])
    assert value['metrics'][0]['peak_demand_kw'] == 100
    assert value['counts']['out_of_range_rows'] == 1 and value['counts']['windows'] == 2
    assert runner.oracle.check(result, ir(), fixture, profile(), 'boundary_records')['pass']


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1])
def test_invalid_energy_rejected(tmp_path, value):
    fixture = inputs(tmp_path / 'inputs')
    data = [json.loads(s) for s in (fixture / 'readings.jsonl').read_text().splitlines()]
    data[0]['energy_kwh'] = value; inputs(fixture, data)
    trace, _ = execute(tmp_path, fixture)
    assert trace['states']['stage_1'] == 'failed'


@pytest.mark.parametrize('field,value', [('window_size_minutes', 0), ('window_size_minutes', True),
                                        ('batch_window_start', '2026-01-01T00:00:00')])
def test_invalid_window_context_not_invented(tmp_path, field, value):
    fixture = inputs(tmp_path / 'inputs'); config = runner.replay.read_json(fixture / 'fixture.json')
    config[field] = value; runner.controls.write_json(fixture / 'fixture.json', config)
    trace, _ = execute(tmp_path, fixture)
    assert trace['states']['stage_1'] == 'failed'


@pytest.mark.parametrize('change', ['missing_link', 'from_alias', 'unknown_profile', 'missing_stage', 'wrong_version'])
def test_unsupported_ir_not_repaired(change):
    value = ir(); before = copy.deepcopy(value)
    if change == 'missing_link': value['artifacts'][0].pop('fixture_ref')
    elif change == 'from_alias': value['control_flow']['edges'][0] = {'from_': 'stage_0', 'to': 'stage_1'}
    elif change == 'unknown_profile': value['bindings'][0]['parameter_bindings']['operation_profile'] = 'invented'
    elif change == 'missing_stage': value['bindings'].pop()
    else: value['bindings'][0]['service_version'] = '9.0.0'
    original = copy.deepcopy(value)
    with pytest.raises(ValueError): runner.engine.compile_ir(value)
    assert value == original


def test_changed_rules_not_silently_interpreted():
    value = profile(); value['rules']['energy'] = 'cumulative'
    with pytest.raises(runner.ops.Unsupported): runner.ops.verify_profile(value)


def test_checker_never_reads_outside_public_fixture_root(tmp_path):
    fixture = inputs(tmp_path / 'inputs')
    config = runner.replay.read_json(fixture / 'fixture.json')
    config['inputs']['readings'] = '../outside.jsonl'
    runner.controls.write_json(fixture / 'fixture.json', config)
    with pytest.raises(ValueError, match='escapes fixture root'):
        runner.oracle.expected(fixture, profile())


def test_sandbox_all_public_scenarios_and_checksum_consistent_negatives(tmp_path):
    active = inputs(tmp_path / 'active')
    runner.prepare_scenarios(active, tmp_path / 'fixtures', profile())
    result, raw = runner.run_ir(ir(), profile(), tmp_path, tmp_path / 'fixtures', tmp_path / 'attempt')
    assert result['profile_all_scenarios_pass'], result
    nominal = next(r for r in raw if r['scenario'] == 'nominal')
    negative = runner.negative_controls(nominal, ir(), tmp_path / 'fixtures/scenarios/nominal', profile(), tmp_path / 'negative')
    assert len(negative) == 4 and all(n['detected'] for n in negative.values()), negative


def test_original_reference_shape_supported_without_private_answers(tmp_path):
    reference = runner.controls.load(ROOT / 'benchmark/instances/extension/building_energy_window_aggregation/gold/serviceflow.yaml')
    before = copy.deepcopy(reference)
    active = inputs(tmp_path / 'active')
    runner.prepare_scenarios(active, tmp_path / 'fixtures', profile())
    workspace = ROOT / 'audit/outputs/controls__20261024T114039Z__9378fab4/cases/extension/building_energy_window_aggregation/public_workspace/extension/building_energy_window_aggregation'
    result, _ = runner.run_ir(reference, profile(), workspace, tmp_path / 'fixtures', tmp_path / 'attempt')
    assert result['profile_all_scenarios_pass'], result
    assert reference == before
