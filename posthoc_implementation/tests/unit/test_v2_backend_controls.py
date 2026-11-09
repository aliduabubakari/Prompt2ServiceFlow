"""Backend-neutral checks require business values, not internal trace/status claims."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_backend_controls as pilot


def control(tmp_path, monkeypatch):
    fixture = tmp_path / 'fixtures'
    fixture.mkdir()
    (fixture / 'records.jsonl').write_text('{"energy":5}\n')
    (fixture / 'registry.csv').write_text('group,capacity\nA,10\n')
    (fixture / 'fixture.json').write_text(json.dumps({'inputs': {'records': 'records.jsonl', 'registry': 'registry.csv'}}))
    profile = {'input_keys': {'records': 'records', 'registry': 'registry'}, 'public_rules': 'unit control'}
    metrics = [{'group_id': 'A', 'window_start': '2026-01-01T00:00:00Z', 'window_end': '2026-01-01T01:00:00Z',
                'record_count': 1, 'energy_kwh_sum': 5.0, 'peak_demand_kw': 2.0,
                'mean_power_factor': .95, 'demand_pct': 20.0, 'high_demand': False, 'low_power_factor': False}]
    counts = {'raw_rows': 1, 'windows': 1}
    monkeypatch.setattr(pilot.real.oracle.base, 'expected', lambda *args: (copy.deepcopy(metrics), copy.deepcopy(counts)))
    ir = {'bindings': [{'service_id': 'timeseries_output_bundle_publisher', 'intent_id': 'publish',
                        'output_bindings': [{'port': 'output_artifacts', 'artifact_id': 'published_bundle'}]}],
          'artifacts': [{'artifact_id': 'published_bundle', 'role': 'output'}]}
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(metrics[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(metrics)
    raw = stream.getvalue().encode()
    audit = {'counts': counts, 'csv_sha256': hashlib.sha256(raw).hexdigest(),
             'profile_sha256': pilot.controls.fingerprint(profile),
             'source_sha256': {'records': pilot.controls.sha256(fixture / 'records.jsonl'),
                               'registry': pilot.controls.sha256(fixture / 'registry.csv')}}
    payload = {'metrics': metrics, 'counts': counts, 'published_files': {'csv': 'published/metrics.csv', 'audit': 'published/audit.json'}}
    result = {'scenario': 'nominal', '_errors': [], '_snapshot': {
        'artifacts/published_bundle.json': json.dumps(payload).encode(),
        'published/metrics.csv': raw, 'published/audit.json': json.dumps(audit).encode()}}
    return result, ir, fixture, profile


def test_good_business_outputs_need_no_internal_backend_trace(tmp_path, monkeypatch):
    args = control(tmp_path, monkeypatch)
    assert 'logs/bounded_window_trace.json' not in args[0]['_snapshot']
    assert pilot.neutral_check(*args)['pass'] is True


@pytest.mark.parametrize('condition', ['constant_summary', 'wrong_energy', 'wrong_alert', 'missing_publication'])
def test_business_mutations_are_detected_with_consistent_checksums(condition, tmp_path, monkeypatch):
    source, ir, fixture, profile = control(tmp_path, monkeypatch)
    before = copy.deepcopy(source)
    mutant = pilot.mutate(source, ir, condition)
    assert source == before
    assert pilot.neutral_check(mutant, ir, fixture, profile)['pass'] is False
    if condition != 'missing_publication':
        audit = json.loads(mutant['_snapshot']['published/audit.json'])
        assert audit['csv_sha256'] == hashlib.sha256(mutant['_snapshot']['published/metrics.csv']).hexdigest()


def test_success_flag_without_business_results_is_not_enough(tmp_path, monkeypatch):
    source, ir, fixture, profile = control(tmp_path, monkeypatch)
    source['_snapshot'] = {'artifacts/published_bundle.json': b'{"success":true}'}
    assert pilot.neutral_check(source, ir, fixture, profile)['pass'] is False


def test_correct_payload_does_not_hide_bad_csv(tmp_path, monkeypatch):
    source, ir, fixture, profile = control(tmp_path, monkeypatch)
    source['_snapshot']['published/metrics.csv'] = b'wrong,columns\n1,2\n'
    assert pilot.neutral_check(source, ir, fixture, profile)['pass'] is False


def test_execution_errors_cannot_be_hidden_by_correct_cached_business_outputs(tmp_path, monkeypatch):
    source, ir, fixture, profile = control(tmp_path, monkeypatch)
    source['_errors'] = ['Execution failed']
    assert pilot.neutral_check(source, ir, fixture, profile)['pass'] is False


def test_source_changes_are_detected_by_public_oracle_or_integrity(tmp_path, monkeypatch):
    source, ir, fixture, profile = control(tmp_path, monkeypatch)
    (fixture / 'records.jsonl').write_text('{"energy":6}\n')
    assert pilot.neutral_check(source, ir, fixture, profile)['pass'] is False


def test_cached_snapshot_checksums_and_inventory_are_strict(tmp_path):
    folder = tmp_path / 'scenario_000'
    folder.mkdir()
    (folder / 'artifact.json').write_text('{}')
    entry = {'directory': 'scenario_000', 'scenario': 'nominal', 'execution_errors': [],
             'artifact_sha256': {'artifact.json': pilot.controls.sha256(folder / 'artifact.json')}}
    assert pilot.restored(entry, tmp_path)['_snapshot']['artifact.json'] == b'{}'
    (folder / 'artifact.json').write_text('{"changed":true}')
    with pytest.raises(ValueError): pilot.restored(entry, tmp_path)


def test_extra_unrecorded_snapshot_file_is_rejected(tmp_path):
    folder = tmp_path / 'scenario_000'
    folder.mkdir()
    (folder / 'extra.json').write_text('{}')
    entry = {'directory': 'scenario_000', 'scenario': 'nominal', 'execution_errors': [], 'artifact_sha256': {}}
    with pytest.raises(ValueError): pilot.restored(entry, tmp_path)


def test_mock_install_cannot_target_existing_directory(tmp_path):
    with pytest.raises(ValueError): pilot.install_mock({}, {}, tmp_path, tmp_path, tmp_path, [])


def test_dry_run_executes_no_workflow_or_model(monkeypatch, capsys):
    monkeypatch.setattr(pilot, 'prepare', lambda: (
        {'positive_scenarios': ['nominal'], 'negative_controls': ['one']}, {}, {'case': 'main/unit'},
        None, None, {'nominal': {}}, {'input': 'sha'}))
    def forbidden(*args, **kwargs): raise AssertionError('No execution during preparation')
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.trace.runtime_compiler, 'materialize_runtime', forbidden)
    monkeypatch.setattr(pilot.subprocess, 'run', forbidden)
    assert pilot.main(['--dry-run']) == 0
    assert '"api_requests": 0' in capsys.readouterr().out
