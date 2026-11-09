"""V2 synthetic regression controls; never consume private expected answers."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'audit'))
sys.path.insert(0, str(ROOT / 'audit/v2'))
import service_executor as executor
import public_bindings
import run_v2_reference_controls as runner


def spec(output_path='/workspace/artifacts/metadata.json'):
    return {'service_id': 'csv_tabular_schema_validating_loader', 'intent_id': 'load_csv',
            'parameters': {'output_path': output_path, 'required_columns': ['name', 'value']},
            'inputs': {'csv_file': {'relative': 'source.csv', 'fixture_ref': 'fixtures/inputs/source.csv', 'suffix': '.csv'}},
            'outputs': [{'port': 'validated_dataset', 'artifact_id': 'dataset', 'suffix': '.json'},
                        {'port': 'validated_data_object', 'artifact_id': 'metadata', 'suffix': '.json'},
                        {'port': 'validation_status', 'artifact_id': 'status', 'suffix': '.json'}]}


@pytest.mark.parametrize('location', ['/workspace/artifacts/metadata.json', 'metadata.json',
                                     '/data/validated/data.json', '/workspace/data.json'])
def test_filename_collision_does_not_overwrite_another_port(tmp_path, location):
    fixtures = tmp_path / 'fixtures'
    fixtures.mkdir()
    (fixtures / 'source.csv').write_text('name,value\na,7\n')
    workspace = tmp_path / 'scratch'
    executor.run(spec(location), workspace, fixtures)
    dataset = json.loads((workspace / 'artifacts/dataset.json').read_text())
    metadata = json.loads((workspace / 'artifacts/metadata.json').read_text())
    assert dataset['rows'] == [{'name': 'a', 'value': '7'}]
    assert 'rows' not in metadata and metadata['record_count'] == 1
    mapping = json.loads((workspace / 'logs/public_output_bindings.json').read_text())
    output = next(o for o in mapping['outputs'] if o['port'] == 'validated_dataset')
    target = workspace / output['materialized_path']
    assert target.read_bytes() == (workspace / output['canonical_path']).read_bytes()
    assert target.resolve().is_relative_to(workspace.resolve())
    assert target != workspace / 'artifacts/metadata.json'


def test_absolute_and_relative_locations_do_not_alias():
    assert executor.logical_path('/data/result.csv') != executor.logical_path('data/result.csv')


@pytest.mark.parametrize('location', ['../output.json', '/data/../output.json', '', '/',
    'folder/', 'a//b', './data.json', 'file:///etc/passwd', '${HOME}/out', '{{ ds }}/out', 'x\\y'])
def test_ambiguous_unsafe_and_unresolved_locations_rejected(location):
    with pytest.raises(ValueError):
        executor.logical_path(location)


def test_host_absolute_label_is_only_a_contained_logical_copy(tmp_path):
    fixtures = tmp_path / 'fixtures'
    fixtures.mkdir()
    (fixtures / 'source.csv').write_text('name,value\na,7\n')
    executor.run(spec('/do-not-create-on-host/output.json'), tmp_path / 'scratch', fixtures)
    assert (tmp_path / 'scratch/service_outputs/load_csv/validated_dataset/absolute/do-not-create-on-host/output.json').is_file()


def test_duplicate_canonical_outputs_rejected_before_any_write(tmp_path):
    specification = spec()
    specification['outputs'][1]['artifact_id'] = 'dataset'
    values = executor.compute(specification['service_id'], specification['parameters'],
        {'csv_file': 'name,value\na,7\n'}, {'csv_file': 'fixtures/inputs/source.csv'})
    with pytest.raises(ValueError, match='collide'):
        executor.plan_writes(specification, values)


def test_public_manifest_preserves_exact_available_file_and_hash(tmp_path):
    root = tmp_path / 'fixtures/scenarios/nominal'
    root.mkdir(parents=True)
    path = root / 'source.csv'
    path.write_text('name,value\na,7\n')
    manifest = public_bindings.build(tmp_path, [{'name': 'nominal', 'fixture_root': 'fixtures/scenarios/nominal'}])
    checks = public_bindings.validate(spec(), manifest)
    assert checks[0]['resolved_fixture_ref'] == 'fixtures/scenarios/nominal/source.csv'
    assert checks[0]['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_no_guessing_missing_bindings_or_similarly_named_files(tmp_path):
    root = tmp_path / 'fixtures/inputs'
    root.mkdir(parents=True)
    (root / 'other_source.csv').write_text('name,value\na,7\n')
    manifest = public_bindings.build(tmp_path, [{'name': 'nominal', 'fixture_root': 'fixtures/inputs'}])
    with pytest.raises(ValueError, match='unavailable'):
        public_bindings.validate(spec(), manifest)
    missing = spec()
    missing['inputs']['csv_file'].pop('fixture_ref')
    with pytest.raises(ValueError, match='absent'):
        public_bindings.validate(missing, manifest)


def test_input_symlinks_cannot_expose_private_files(tmp_path):
    root = tmp_path / 'fixtures/inputs'
    root.mkdir(parents=True)
    secret = tmp_path / 'private.json'
    secret.write_text('{}')
    (root / 'leak.json').symlink_to(secret)
    with pytest.raises(ValueError, match='escapes'):
        public_bindings.build(tmp_path, [{'name': 'nominal', 'fixture_root': 'fixtures/inputs'}])


def test_v2_sandbox_collision_and_changed_input(tmp_path):
    workspace = tmp_path / 'public'
    fixtures = workspace / 'fixtures/inputs'
    fixtures.mkdir(parents=True)
    (fixtures / 'source.csv').write_text('name,value\na,7\n')
    from unittest.mock import patch
    with patch.object(runner.replay, 'executor', executor), patch.object(runner.replay, 'install', runner.install_v2):
        result = runner.replay.invoke(spec(), workspace, tmp_path / 'attempt')
    assert result['state'] == 'executed', result
    assert result['input_probe']['pass']
    assert all(c['pass'] for c in runner.check_paths(tmp_path / 'attempt'))
    assert result['g6_assert'] == 'not_measured'


def test_exporter_keeps_requested_uri_and_csv_bytes(tmp_path):
    specification = {'service_id': 'structured_json_to_csv_exporter', 'intent_id': 'export_csv',
        'parameters': {'output_filename': '/data/output.csv'},
        'outputs': [{'port': 'csv_file', 'artifact_id': 'table', 'suffix': '.csv'},
                    {'port': 'export_status', 'artifact_id': 'status', 'suffix': '.json'}]}
    values = executor.compute(specification['service_id'], specification['parameters'],
        {'structured_json': {'columns': ['name'], 'rows': [{'name': 'a,b'}]}}, {})
    writes, mapping = executor.plan_writes(specification, values)
    assert writes['artifacts/table.csv'] == b'name\n"a,b"\n'
    assert json.loads(writes['artifacts/status.json'])['output_uri'] == '/data/output.csv'
    copied = next(o for o in mapping['outputs'] if o['port'] == 'csv_file')
    assert writes[copied['materialized_path']] == writes['artifacts/table.csv']
