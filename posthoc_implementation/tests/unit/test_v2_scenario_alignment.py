"""Synthetic provenance tests; no original workflow or predicate execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'audit/v2'), str(ROOT / 'audit')]
import audit_v2_scenario_alignment as runner

a = runner.analysis


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))


def context(params=None, files=None, state='present'):
    return {'parameters': {} if params is None else params, 'fixture_tree': {'state': state, 'files': {'data.csv': 'abc'} if files is None else files}}


def test_unique_context_alias_is_only_input_association():
    result = a.associate([{'scenario': 'nominal'}], {'nominal': context({'value': True})},
        {'positive': context({'value': True}), 'negative': context({'value': False})}, True)
    assert [(p['execution'], p['reviewed']) for p in result['supported_input_associations']] == [('nominal', 'positive')]
    assert result['reviewed_scenarios_without_supported_association'] == ['negative']
    assert result['additional_recorded_executions_required_lower_bound'] == 1


@pytest.mark.parametrize('left,right', [({}, {'flag': True}), ({'flag': True}, {'flag': 1}), ({'x': '1'}, {'x': 1}),
    ({'date': 'Saturday'}, {'date': 'Monday'}), ({'nested': {'flag': True}}, {'nested': {'flag': 1}})])
def test_exact_parameters_are_not_defaults_or_python_coercions(left, right):
    assert not a.context_comparison(context(left), context(right))['context_exact']


@pytest.mark.parametrize('left,right', [({'data.csv': 'a'}, {'data.csv': 'b'}),
    ({'data.csv': 'a', 'fixture.json': 'x'}, {'data.csv': 'a'}), ({'one/data.csv': 'a'}, {'two/data.csv': 'a'})])
def test_matching_one_file_or_basename_does_not_establish_full_fixture_identity(left, right):
    assert not a.context_comparison(context(files=left), context(files=right))['fixture_tree_exact']


def test_missing_fixture_roots_cannot_match_as_two_empty_dicts():
    assert not a.context_comparison(context(files={}, state='missing'), context(files={}, state='missing'))['context_exact']


def test_two_context_candidates_are_ambiguous_not_chosen_by_position():
    result = a.associate([{'scenario': 'nominal'}], {'nominal': context()}, {'one': context(), 'two': context()}, True)
    assert not result['supported_input_associations'] and len(result['reviewed_scenarios_without_supported_association']) == 2


def test_two_executions_cannot_both_claim_the_same_reviewed_context():
    result = a.associate([{'scenario': 'first'}, {'scenario': 'second'}], {'first': context(), 'second': context()}, {'reviewed': context()}, True)
    assert not result['supported_input_associations']


def test_exact_name_does_not_override_different_input_context():
    result = a.associate([{'scenario': 'same'}], {'same': context({'v': False})}, {'same': context({'v': True})}, True)
    assert not result['supported_input_associations']


def test_verified_exact_named_context_is_preserved():
    result = a.associate([{'scenario': 'same'}], {'same': context()}, {'same': context()}, True)
    assert result['supported_input_associations'][0]['association'] == 'exact_name_and_context'
    assert not result['reviewed_scenarios_without_supported_association']


def test_unverified_workspace_or_missing_declaration_cannot_authorize_alias():
    assert not a.associate([{'scenario': 'x'}], {'x': context()}, {'y': context()}, False)['supported_input_associations']
    assert not a.associate([{'scenario': 'x'}], {}, {'y': context()}, True)['supported_input_associations']


def test_duplicate_recorded_scenarios_are_not_double_counted():
    with pytest.raises(ValueError, match='Duplicate'): a.associate([{'scenario': 'x'}, {'scenario': 'x'}], {'x': context()}, {'y': context()}, True)


def test_fixture_inventory_rejects_symlinks_limits_and_escape(tmp_path):
    directory = tmp_path / 'fixtures'; directory.mkdir(); (directory / 'data.csv').write_text('data')
    with pytest.raises(ValueError, match='limit'): a.tree(directory, max_bytes=1)
    (directory / 'link').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError, match='Symlink'): a.tree(directory)
    with pytest.raises(ValueError): a.bounded.safe(directory, '../outside')


def test_runtime_fixture_default_is_recorded_without_guessing(tmp_path):
    fallback, policy = a.fixture_root(tmp_path, {'name': 'nominal'})
    assert fallback == tmp_path / 'fixtures/inputs' and policy == 'runtime_fallback'
    (tmp_path / 'fixtures/scenarios/nominal').mkdir(parents=True)
    conventional, policy = a.fixture_root(tmp_path, {'name': 'nominal'})
    assert conventional == tmp_path / 'fixtures/scenarios/nominal' and policy == 'runtime_convention'


def synthetic(tmp_path, raw_pass=True):
    workspace = tmp_path / 'public'; sub = tmp_path / 'run/submission'; instance = tmp_path / 'benchmark/instances/main/example'
    write(workspace / 'fixtures/scenarios/nominal/input.json', {'v': 1})
    file = workspace / 'fixtures/scenarios/nominal/input.json'
    write(workspace / 'workspace.yaml', {'files': [{'path': str(file.relative_to(workspace)), 'sha256': a.sha(file)}]})
    write(sub / 'runtime/manifest.yaml', {'scenarios': [{'name': 'nominal', 'parameters': {}, 'fixture_root': 'fixtures/scenarios/nominal'}]})
    write(instance / 'runtime/manifest.yaml', {'scenarios': [
        {'name': 'present', 'parameters': {'available': True}, 'fixture_root': 'fixtures/inputs'},
        {'name': 'missing', 'parameters': {'available': False}, 'fixture_root': 'fixtures/inputs'}]})
    write(instance / 'fixtures/inputs/input.json', {'v': 1})
    write(instance / 'gold/assertions.yaml', {'scenarios': [{'scenario': n, 'assertions': [{'assertion_id': n, 'path': 'artifacts/result.json'}]} for n in ['present', 'missing']]})
    manifest_path = tmp_path / 'run/manifest.json'; score_path = tmp_path / 'run/score.json'
    write(manifest_path, {'workspace_manifest_sha256': a.sha(workspace / 'workspace.yaml'), 'evaluation': {'score_summary': {'full_pass_g0_g6': raw_pass}}})
    write(score_path, {'workspace': str(workspace), 'submission': str(sub)})
    cell = {'id': 'synthetic/m4/main/example/0', 'model': 'synthetic', 'method': 'm4', 'case': 'main/example', 'sample_index': 0,
            'score_path': str(score_path), 'saved_ir_path': str(sub / 'serviceflow.yaml')}
    row = {'manifest_path': str(manifest_path), 'semantic_source': 'posthoc_scorer_1.2.1', 'semantic_success': '0'}
    post = {'semantic_success': False, 'g6_assert': {'scenarios': [{'scenario': 'nominal', 'execution_status': 'pass', 'assertions': [], 'scoring_error': 'no match'}]}}
    return cell, row, post, tmp_path / 'benchmark', workspace


@pytest.mark.parametrize('raw_pass', [True, False])
def test_full_inspection_preserves_published_nonpass_and_missing_coverage(tmp_path, raw_pass):
    args = synthetic(tmp_path, raw_pass); result = a.inspect(*args)
    assert result['public_provenance']['verified'] is True
    assert result['additional_recorded_executions_required_lower_bound'] == 1
    assert len(result['reviewed_scenarios_without_supported_association']) == 2
    assert not result['supported_input_associations'] and result['new_semantic_score'] is None and not result['rescored']
    assert result['published_semantic_success'] is False and result['raw_manifest_full_pass_flag'] is raw_pass


def test_loose_output_is_not_a_provenanced_execution_snapshot(tmp_path):
    args = synthetic(tmp_path); sub = Path(args[0]['saved_ir_path']).parent
    write(sub / 'artifacts/result.json', {'success': True})
    result = a.inspect(*args)
    assert result['retained_outputs']['loose_expected_files_present'] == 1
    assert not result['retained_outputs']['provenance_bound_snapshot_available']
    assert not result['retained_outputs']['offline_rescoring_authorized']


@pytest.mark.parametrize('change', ['bytes', 'extra_file', 'manifest'])
def test_original_workspace_hash_and_complete_inventory_must_match(tmp_path, change):
    args = synthetic(tmp_path); workspace = args[-1]
    if change == 'bytes': write(workspace / 'fixtures/scenarios/nominal/input.json', {'v': 9})
    elif change == 'extra_file': write(workspace / 'fixtures/scenarios/nominal/additional.json', {})
    else: write(workspace / 'workspace.yaml', {'files': []})
    assert a.inspect(*args)['public_provenance']['verified'] is False


def test_inspection_never_executes_retained_script(tmp_path):
    args = synthetic(tmp_path); sub = Path(args[0]['saved_ir_path']).parent; sentinel = tmp_path / 'must_not_exist'
    script = sub / 'runtime/scripts/untrusted.py'; script.parent.mkdir(parents=True)
    script.write_text('from pathlib import Path\nPath(' + repr(str(sentinel)) + ').touch()\nraise RuntimeError("must not execute")\n')
    runtime = a.document(sub / 'runtime/manifest.yaml')
    runtime['tasks'] = [{'intent_id': 'untrusted', 'script': 'scripts/untrusted.py', 'arguments': []}]
    write(sub / 'runtime/manifest.yaml', runtime)
    a.inspect(*args)
    assert not sentinel.exists()


def test_missing_and_duplicate_scenario_declarations_are_errors(tmp_path):
    args = synthetic(tmp_path); path = Path(args[0]['saved_ir_path']).parent / 'runtime/manifest.yaml'
    write(path, {'scenarios': [{'name': 'x', 'parameters': {}}, {'name': 'x', 'parameters': {}}]})
    with pytest.raises(ValueError, match='Duplicate'): a.inspect(*args)


def test_directory_inventory_changes_are_detected(tmp_path):
    directory = tmp_path / 'fixtures'; directory.mkdir(); (directory / 'one').write_text('one')
    snapshot = {str(directory): a.tree(directory)}; runner.verify_directories(snapshot)
    (directory / 'two').write_text('two')
    with pytest.raises(ValueError, match='inventory changed'): runner.verify_directories(snapshot)
