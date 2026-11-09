"""Frozen scope, honest denominators and resumable offline batch orchestration."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_frozen_semantic_replay as runner

spec = importlib.util.spec_from_file_location('resolution_examples', ROOT / 'tests/unit/test_v2_semantic_resolution.py')
examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examples)


def cell(path, case='extension/synthetic', method='m4', sample=0):
    return {'source': {'id': f'unit/{method}/{case}/{sample}', 'model': 'unit', 'method': method,
            'case': case, 'sample_index': sample, 'route': 'direct_argo' if method in ('m0', 'm1', 'm2') else 'serviceflow_ir',
            'artifact': str(path), 'original_method_status': 'completed'},
            'artifact_sha256': runner.controls.sha256(path) if path.is_file() else 'MISSING',
            'analysis': {'state': 'inspected'}}


def preparation(tmp_path, value=None):
    value = examples.synthetic_ir() if value is None else value
    value['source'] = {'split': 'extension', 'pipeline_id': 'synthetic'}
    path = tmp_path / 'saved_ir.json'
    path.write_text(json.dumps(value))
    return cell(path), {'profile_bindings': {'extension/synthetic': {'profile_version': 'bounded-window-1'}},
        'projection': examples.contract(), 'policy': examples.policy(), 'workspace': tmp_path,
        'schema': {}, 'context': {}, 'profile': {}, 'fixtures': tmp_path, 'scenario_design': {}}


@pytest.mark.parametrize('mutation,expected', [('mock', 'runtime_selection_not_reference'),
    ('default', 'operation_label_not_registered'), ('service', 'unregistered_service_version'),
    ('identity', 'saved_source_identity_mismatch')])
def test_old_runtime_or_operation_meanings_are_never_silently_replaced(mutation, expected, tmp_path, monkeypatch):
    value = examples.synthetic_ir()
    if mutation == 'mock': value['runtime']['execution_profile'] = 'mock'
    if mutation == 'default': value['bindings'][0]['parameter_bindings']['operation_profile'] = 'default'
    if mutation == 'service': value['bindings'][0]['service_version'] = '99.0.0'
    source, prepared = preparation(tmp_path, value)
    if mutation == 'identity':
        original = json.loads(Path(source['source']['artifact']).read_text())
        original['source']['pipeline_id'] = 'another'
        Path(source['source']['artifact']).write_text(json.dumps(original))
    before = Path(source['source']['artifact']).read_bytes()
    def forbidden(*args, **kwargs): raise AssertionError('No guessed completion or workflow')
    monkeypatch.setattr(runner.resolution.semantic_completion, 'complete', forbidden)
    monkeypatch.setattr(runner.pilot, 'run_condition', forbidden)
    plan = runner.plan_cell(source, prepared)
    assert plan['state'] == 'incompatible_explicit_execution_contract'
    assert expected in {b['code'] for b in plan['blockers']}
    assert plan['conditions'] == {}
    assert Path(source['source']['artifact']).read_bytes() == before


def test_direct_argo_is_not_converted_or_given_a_semantic_failure(tmp_path):
    source = cell(tmp_path / 'absent.yaml', method='m2')
    plan = runner.plan_cell(source, {})
    assert plan['state'] == 'not_applicable_direct_argo' and not plan['conditions']
    assert runner.aggregate([plan]) == []


@pytest.mark.parametrize('availability,state', [('missing', 'missing_saved_ir'), ('invalid', 'unreadable_or_invalid_saved_ir')])
def test_unavailable_saved_outputs_stay_in_coverage(availability, state, tmp_path):
    source = cell(tmp_path / 'saved.json')
    if availability == 'invalid':
        source['artifact_sha256'] = 'known_invalid_document_hash'
        source['analysis']['state'] = 'parse_error'
    plan = runner.plan_cell(source, {})
    assert plan['state'] == state
    group = runner.aggregate([plan])[0]
    assert group['declared'] == group['not_evaluated'] == 1
    assert group['evaluated'] == 0 and group['evaluated_pass_rate'] is None


def test_similar_service_roster_does_not_assign_a_new_task_profile(tmp_path):
    source, prepared = preparation(tmp_path)
    source['source']['case'] = 'validation/different_task'
    assert runner.plan_cell(source, prepared)['state'] == 'unsupported_task_profile'


def ready_plan(tmp_path, monkeypatch):
    source, prepared = preparation(tmp_path)
    monkeypatch.setattr(runner.census, 'Catalog', lambda: SimpleNamespace(get=lambda workspace, s, v: examples.catalog_get(s, v)))
    monkeypatch.setattr(runner.pilot, 'inspect_candidate', lambda *args: {'state': 'ready'})
    row = runner.plan_cell(source, prepared)
    assert row['state'] == 'planned'
    return row, prepared


def test_typed_completion_is_separate_from_raw_and_retains_source(tmp_path, monkeypatch):
    row, _ = ready_plan(tmp_path, monkeypatch)
    raw = row['conditions']['raw']
    completed = row['conditions']['frozen_completion']
    assert raw['candidate_ir'] != completed['candidate_ir']
    assert len(completed['assembly']['operations']) == 1
    assert raw['assembly']['operations'] == []
    assert raw['candidate_ir']['bindings'][-1]['output_bindings'] == completed['candidate_ir']['bindings'][-1]['output_bindings'][:-1]


def test_identical_conditions_reuse_one_execution_explicitly(tmp_path, monkeypatch):
    row, prepared = ready_plan(tmp_path, monkeypatch)
    row['conditions']['frozen_completion']['candidate_ir'] = copy.deepcopy(row['conditions']['raw']['candidate_ir'])
    calls = []
    def execute(*args):
        calls.append(1)
        return {'state': 'evaluated', 'evaluated': True, 'profile_all_controls_pass': True}
    monkeypatch.setattr(runner.pilot, 'run_condition', execute)
    result = runner.run_cell(row, tmp_path / 'attempt', prepared)
    assert len(calls) == 1
    assert result['conditions']['frozen_completion']['execution_reused_from'] == 'raw'


def test_different_conditions_are_not_counted_as_independent_model_samples(tmp_path, monkeypatch):
    row, prepared = ready_plan(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(runner.pilot, 'run_condition', lambda *args: (calls.append(1) or
        {'state': 'evaluated', 'evaluated': True, 'profile_all_controls_pass': True}))
    result = runner.run_cell(row, tmp_path / 'attempt', prepared)
    assert len(calls) == 2
    groups = runner.aggregate([result])
    assert len(groups) == 2 and all(g['declared'] == 1 for g in groups)


def test_evaluated_failures_missing_and_unexecuted_cells_have_distinct_denominators(tmp_path):
    rows = []
    for i, state in enumerate(('pass', 'fail', 'missing', 'unsupported')):
        source = cell(tmp_path / str(i), sample=i)
        evaluated = state in ('pass', 'fail')
        rows.append({'source': source['source'], 'state': state, 'conditions': {
            'raw': {'evaluated': evaluated, 'profile_all_controls_pass': state == 'pass' if evaluated else None}}, 'blockers': []})
    groups = runner.aggregate(rows)
    raw = next(g for g in groups if g['condition'] == 'raw')
    assert raw['declared'] == 4 and raw['evaluated'] == 2 and raw['passed'] == 1
    assert raw['evaluated_pass_rate'] == .5 and raw['coverage'] == .5 and raw['declared_pass_yield'] == .25
    completed = next(g for g in groups if g['condition'] == 'frozen_completion')
    assert completed['evaluated_pass_rate'] is None


@pytest.mark.parametrize('mutation', ['status', 'design', 'evidence', 'profile_binding', 'file'])
def test_freeze_rejects_changes(mutation, tmp_path, monkeypatch):
    target = tmp_path / 'runtime.py'
    target.write_text('frozen')
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'local_implementations', lambda: [target])
    prepared = {'design': {'x': 1}, 'profile_bindings': {'case': 'p'}, 'hashes': {'input': 'hash'}}
    frozen = {'status': 'frozen', 'freeze_format_version': 1, 'design': prepared['design'],
        'profile_bindings': prepared['profile_bindings'], 'evidence_fingerprint': runner.controls.fingerprint(prepared['hashes']),
        'files_sha256': {'runtime.py': runner.controls.sha256(target)}, 'environment': runner.controls.environment()}
    runner.verify_freeze(frozen, prepared)
    frozen = copy.deepcopy(frozen)
    if mutation == 'status': frozen['status'] = 'candidate'
    if mutation == 'design': frozen['design']['x'] = 2
    if mutation == 'evidence': prepared['hashes']['input'] = 'different'
    if mutation == 'profile_binding': prepared['profile_bindings'] = {'case': 'another'}
    if mutation == 'file': target.write_text('changed')
    with pytest.raises(ValueError): runner.verify_freeze(frozen, prepared)


def install_batch(tmp_path, monkeypatch, error=False):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    freeze = tmp_path / 'freeze.json'
    freeze.write_text(json.dumps({'freeze_id': 'unit', 'files_sha256': {}}))
    monkeypatch.setattr(runner, 'FREEZE', freeze)
    cells = [cell(tmp_path / 'not_present', case='main/a', sample=0),
             cell(tmp_path / 'not_present', case='extension/b', sample=1)]
    prepared = {'design': {'package_version': 'unit', 'audit_protocol_version': 'unit'},
                'cells': cells, 'cases': ['main/a', 'extension/b'], 'hashes': {}}
    monkeypatch.setattr(runner, 'verified_evidence', lambda: copy.deepcopy(prepared))
    monkeypatch.setattr(runner, 'verify_freeze', lambda *args: None)
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='tests', stderr=''))
    calls = []
    base_run = runner.run_cell
    def run(row, *args):
        calls.append(row['source']['id'])
        result = base_run(row, *args)
        if error: result['conditions']['raw'] = {'state': 'runtime_or_inspection_error', 'evaluated': False}
        return result
    monkeypatch.setattr(runner, 'run_cell', run)
    return calls


@pytest.mark.parametrize('error', [False, True])
def test_batch_resume_reuses_verified_case_checkpoints_without_redispatch(error, tmp_path, monkeypatch):
    calls = install_batch(tmp_path, monkeypatch, error)
    assert runner.main([]) == int(error)
    output = next((tmp_path / 'audit/outputs').iterdir())
    assert len(calls) == 2
    assert runner.main(['--resume', str(output)]) == int(error)
    assert len(calls) == 2
    results = json.loads((output / 'results.json').read_text())
    assert len(results) == 2
    assert json.loads((output / 'run.json').read_text())['source_inputs_unchanged'] is True


def test_resume_rejects_changed_completed_case(tmp_path, monkeypatch):
    install_batch(tmp_path, monkeypatch)
    runner.main([])
    output = next((tmp_path / 'audit/outputs').iterdir())
    (output / 'cases/main/a/result.json').write_text('[]')
    with pytest.raises(ValueError): runner.main(['--resume', str(output)])


def test_dry_run_cannot_dispatch_inference_or_workflows(tmp_path, monkeypatch, capsys):
    install_batch(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('Preflight cannot execute')
    monkeypatch.setattr(runner.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(runner.pilot, 'run_condition', forbidden)
    monkeypatch.setattr(runner.subprocess, 'run', forbidden)
    assert runner.main(['--dry-run']) == 0
    assert '"ready_ir_cells": 0' in capsys.readouterr().out
    assert not (tmp_path / 'audit').exists()
