"""Fixed-cohort selection, integrity, and sandbox replay regression tests."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_model_replay as runner

SERVICE = 'csv_tabular_schema_validating_loader'


def inventory(states=('executed', 'execution_error', 'unsupported_operation', 'invalid_binding_or_input')):
    sources, results = [], {}
    for index, state in enumerate(states):
        source = {'id': f'model/m4/main/example/{index}', 'kind': 'model', 'method': 'm4',
                  'case': 'main/example', 'model': 'model', 'sample_index': index, 'ir': '/unused'}
        sources.append(source)
        results[source['id']] = {'state': 'inventoried', 'invocations': [
            {'intent_id': 'read_csv', 'service_id': SERVICE, 'service_version': '1.0.0', 'state': state},
            {'intent_id': 'unknown', 'service_id': 'not_implemented', 'service_version': '1.0.0', 'state': 'unsupported_service'}]}
    return {'sources': sources, 'results': results}


def test_selection_retains_every_prior_outcome_and_source_unchanged():
    original = inventory()
    before = copy.deepcopy(original)
    targets, ledger = runner.make_plan(original)
    assert len(targets) == len(ledger) == 4
    assert {t['prior_state'] for t in targets} == {'executed', 'execution_error', 'unsupported_operation', 'invalid_binding_or_input'}
    assert all(x['out_of_scope_invocations'] == 1 for x in ledger)
    assert original == before


def test_missing_and_invalid_ir_remain_in_coverage_ledger():
    original = inventory(('executed',))
    for state in ('missing_saved_ir', 'invalid_saved_ir'):
        source = {'id': state, 'kind': 'model', 'model': 'model', 'method': 'm4'}
        original['sources'].append(source)
        original['results'][state] = {'state': state, 'invocations': []}
    targets, ledger = runner.make_plan(original)
    assert len(targets) == 1 and len(ledger) == 3
    assert sum(not row['target_ids'] for row in ledger) == 2


def test_references_and_wrong_versions_not_selected():
    original = inventory(('executed',))
    original['sources'].append({'id': 'reference', 'kind': 'reference'})
    original['results'][original['sources'][0]['id']]['invocations'][0]['service_version'] = '2.0.0'
    targets, ledger = runner.make_plan(original)
    assert not targets and len(ledger) == 1
    assert ledger[0]['out_of_scope_invocations'] == 2


def test_duplicate_invocation_rejected():
    original = inventory(('executed',))
    result = next(iter(original['results'].values()))
    result['invocations'].append(copy.deepcopy(result['invocations'][0]))
    with pytest.raises(ValueError, match='Duplicate target'):
        runner.make_plan(original)


def test_duplicate_source_identity_rejected():
    original = inventory(('executed',))
    original['sources'].append(original['sources'][0])
    with pytest.raises(ValueError, match='Duplicate inventory source'):
        runner.make_plan(original)


def test_hash_manifest_and_source_changes_detected(tmp_path):
    source = tmp_path / 'saved.yaml'
    source.write_text('unchanged')
    hashes = {str(source): runner.controls.sha256(source)}
    runner.controls.write_json(tmp_path / 'input_sha256.json', hashes)
    record = {'input_fingerprint': runner.controls.fingerprint(hashes)}
    assert runner.verify_hashes(tmp_path, record) == hashes
    source.write_text('changed')
    with pytest.raises(ValueError, match='Immutable input changed'):
        runner.verify_hashes(tmp_path, record)
    runner.controls.write_json(tmp_path / 'input_sha256.json', {})
    with pytest.raises(ValueError, match='manifest does not match'):
        runner.verify_hashes(tmp_path, record)


def test_previously_missing_source_appearing_is_a_protocol_change(tmp_path):
    path = tmp_path / 'missing.yaml'
    hashes = {str(path): 'MISSING'}
    runner.controls.write_json(tmp_path / 'input_sha256.json', hashes)
    record = {'input_fingerprint': runner.controls.fingerprint(hashes)}
    runner.verify_hashes(tmp_path, record)
    path.write_text('{}')
    with pytest.raises(ValueError, match='Immutable input changed'):
        runner.verify_hashes(tmp_path, record)


def saved_target(tmp_path, *, fixture_ref='fixtures/inputs/source.csv', required_columns=None):
    workspace = tmp_path / 'baseline/cases/main/synthetic/public_workspace/main/synthetic'
    fixtures = workspace / 'fixtures/inputs'
    fixtures.mkdir(parents=True)
    (fixtures / 'source.csv').write_text('name,value\na,7\n')
    binding = {'intent_id': 'read_csv', 'service_id': SERVICE, 'service_version': '1.0.0',
               'input_bindings': [{'port': 'csv_file', 'artifact_id': 'source'}],
               'output_bindings': [], 'parameter_bindings': {'output_path': '/workspace/artifacts/metadata.json',
                                                            'required_columns': required_columns or ['name', 'value']}}
    artifact = {'artifact_id': 'source', 'producer': None, 'data_type': 'csv'}
    if fixture_ref is not None:
        artifact['fixture_ref'] = fixture_ref
    ir = {'artifacts': [artifact], 'bindings': [binding]}
    for port, identity in [('validated_dataset', 'data'), ('validated_data_object', 'metadata'), ('validation_status', 'status')]:
        ir['artifacts'].append({'artifact_id': identity, 'producer': 'read_csv', 'data_type': 'json'})
        binding['output_bindings'].append({'port': port, 'artifact_id': identity})
    path = tmp_path / 'final_serviceflow.yaml'
    path.write_text(json.dumps(ir))
    target = {'id': 'target_0000', 'intent_id': 'read_csv', 'service_id': SERVICE, 'service_version': '1.0.0',
              'prior_state': 'execution_error', 'source': {'ir': str(path), 'case': 'main/synthetic'}}
    return target, tmp_path / 'baseline', path


def test_synthetic_saved_replay_repairs_path_not_original_bindings(tmp_path):
    target, baseline, original = saved_target(tmp_path)
    before = original.read_bytes()
    result = runner.run_target(target, baseline, tmp_path / 'attempt')
    assert result['state'] == 'executed', result
    assert result['output_path_pass'] and result['input_probe']['pass']
    assert result['g6_assert'] == 'not_measured'
    assert original.read_bytes() == before


def test_wrong_required_columns_still_fail_without_invented_data(tmp_path):
    target, baseline, original = saved_target(tmp_path, required_columns=['missing_business_column'])
    result = runner.run_target(target, baseline, tmp_path / 'attempt')
    assert result['state'] == 'execution_error'
    assert any('missing required columns' in e for e in result['execution_errors'])


def test_missing_fixture_reference_is_not_filled_in(tmp_path):
    target, baseline, _ = saved_target(tmp_path, fixture_ref=None)
    result = runner.run_target(target, baseline, tmp_path / 'attempt')
    assert result['state'] == 'unsupported_operation'
    assert result['reason'] == 'external_fixture_binding_missing'


def test_unavailable_explicit_fixture_remains_blocked(tmp_path):
    target, baseline, _ = saved_target(tmp_path, fixture_ref='fixtures/inputs/absent.csv')
    result = runner.run_target(target, baseline, tmp_path / 'attempt')
    assert result['state'] == 'blocked_public_input'


def test_mapping_verification_rejects_missing_port_even_if_no_files_changed(tmp_path):
    target, baseline, _ = saved_target(tmp_path)
    runner.run_target(target, baseline, tmp_path / 'attempt')
    root = tmp_path / 'attempt/execution'
    mapping_path = root / 'base_execution/scenario_000/logs/public_output_bindings.json'
    mapping = runner.replay.read_json(mapping_path)
    mapping['outputs'] = []
    runner.controls.write_json(mapping_path, mapping)
    specification = runner.replay.read_json(tmp_path / 'attempt/adapter_spec.json')
    assert not all(c['pass'] for c in runner.verify_mapping(root, specification, True))


def test_summary_keeps_prior_failure_and_missing_coverage_visible():
    targets, ledger = runner.make_plan(inventory(('execution_error',)))
    run = {'package_version': '2', 'audit_protocol_version': '4.1', 'status': 'complete',
           'targets': targets, 'results': {'target_0000': {'state': 'executed'}}}
    text = runner.render(run, ledger)
    assert 'execution_error | executed' in text
    assert 'not G6-Assert' in text
