"""Single-call orchestration, explicit assembly, and execution boundaries."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_generation_pilot as pilot


def model():
    return {'model_name': 'unit', 'base_url': 'http://localhost:1234/v1', 'api_key_env': 'UNIT_TOKEN',
            'max_tokens': 16384, 'temperature': .2, 'top_p': 1, 'seed': 101, 'request_timeout_s': 30}


def test_public_request_exposes_profile_and_policy_without_any_reference_argument(monkeypatch):
    base = [{'role': 'system', 'content': 'public generation'}, {'role': 'user', 'content': 'public task/schema'}]
    monkeypatch.setattr(pilot.generation, 'messages', lambda *args: copy.deepcopy(base))
    request = pilot.build_request(model(), None, {}, {}, {}, {}, {'profile_version': 'public_profile'},
                                  {'fixture_ref': 'fixtures/inputs/fixture.json'}, {'policy_version': 'declared'})
    text = request['messages'][1]['content']
    assert 'PUBLIC NUMERICAL PROFILE' in text
    assert 'REGISTERED SERVICE OPERATIONS' in text
    assert 'fixtures/inputs/fixture.json' in text
    assert 'DECLARED ASSEMBLY POLICY' in text
    assert 'gold/serviceflow.yaml' not in text and 'gold/assertions.yaml' not in text
    assert 'cached_real_profile_execution' not in text
    assert request['max_tokens'] == 16384 and request['seed'] == 101
    assert base[1]['content'] == 'public task/schema'


def test_production_or_mock_runtime_selection_is_not_silently_reinterpreted():
    for value in ('production', 'mock'):
        record = pilot.inspect_candidate({'runtime': {'execution_profile': value}}, {}, None, {}, {})
        assert record['state'] == 'unsupported_runtime_selection'


def test_schema_failure_stops_before_backend_or_catalog(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('No runtime for malformed IR')
    monkeypatch.setattr(pilot.integration.backend, 'compile_plan', forbidden)
    record = pilot.inspect_candidate({}, {'type': 'object', 'required': ['runtime']}, None, {}, {})
    assert record['state'] == 'blocked_schema'


def test_recorded_static_defects_stop_before_execution(monkeypatch):
    monkeypatch.setattr(pilot.generation.census.analysis, 'analyze', lambda *args, **kwargs: {
        'findings': [{'category': 'dataflow', 'code': 'missing_artifact'}], 'finding_counts': {'dataflow': 1}})
    def forbidden(*args, **kwargs): raise AssertionError('No runtime with checked hard defects')
    monkeypatch.setattr(pilot.integration.backend, 'compile_plan', forbidden)
    record = pilot.inspect_candidate({'runtime': {'execution_profile': 'reference'}}, {}, None, {'scenarios': []}, {})
    assert record['state'] == 'blocked_public_contracts'


def test_unknown_registry_scope_is_not_filled_from_reference(monkeypatch):
    monkeypatch.setattr(pilot.generation.census.analysis, 'analyze', lambda *args, **kwargs: {'findings': [], 'finding_counts': {}})
    def unsupported(*args): raise pilot.integration.backend.ops.Unsupported('unknown service')
    monkeypatch.setattr(pilot.integration.backend, 'compile_plan', unsupported)
    record = pilot.inspect_candidate({'runtime': {'execution_profile': 'reference'}}, {}, None, {'scenarios': []}, {})
    assert record['state'] == 'unsupported_runtime_scope'


def test_ambiguous_isolated_execution_is_not_automatically_repeated(tmp_path, monkeypatch):
    (tmp_path / 'execution_started.json').write_text('{}')
    def forbidden(*args, **kwargs): raise AssertionError('No redispatch')
    monkeypatch.setattr(pilot.integration.backend, 'materialize_runtime', forbidden)
    record = pilot.run_condition(tmp_path, {}, {}, None, {}, {}, None, {}, {'operations': []})
    assert record['state'] == 'interrupted_execution_unknown'
    assert record['evaluated'] is False


def test_blocked_condition_is_retained_without_workflow_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'inspect_candidate', lambda *args: {'state': 'blocked_public_contracts', 'hard_finding_count': 2})
    def forbidden(*args, **kwargs): raise AssertionError('No execution')
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    record = pilot.run_condition(tmp_path, {}, {}, None, {}, {}, None, {}, {'operations': []})
    assert record['state'] == 'blocked_public_contracts'
    assert record['profile_all_controls_pass'] is None
    assert (tmp_path / 'result.json').is_file()


def install_fake_preparation(monkeypatch, tmp_path, eligible):
    design = {'case': 'extension/unit', 'conditions': ['raw', 'assembled'],
              'positive_scenarios': ['nominal'], 'rejection_scenarios': [],
              'profile': 'not_read_on_resume', 'assembly_policy': 'not_read_on_resume'}
    request = {'model': 'unit', 'messages': []}
    hashes = {}
    prepared = (design, 'unit', model(), tmp_path / 'public', {}, {}, {}, None, {}, {}, {}, tmp_path / 'source', request, hashes)
    monkeypatch.setattr(pilot, 'prepare', lambda *args: prepared)
    monkeypatch.setenv('UNIT_TOKEN', 'unit-secret')
    run = {'audit_protocol_version': 'unit', 'design': design, 'model_id': 'unit', 'request': request,
           'input_fingerprint': pilot.controls.fingerprint(hashes), 'conditions': {}, 'result_files': {}}
    pilot.controls.write_json(tmp_path / 'run.json', run)
    pilot.controls.write_json(tmp_path / 'input_sha256.json', hashes)
    monkeypatch.setattr(pilot.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='local gate', stderr=''))
    calls = []
    def fake_call(attempt, *args):
        calls.append(1)
        attempt.mkdir(parents=True, exist_ok=True)
        if eligible:
            pilot.controls.write_json(attempt / 'expanded_ir.json', {'unit': 'same decision'})
        return {'status': 'complete_ir' if eligible else 'syntax_error',
                'schema_conformant': eligible, 'metadata_conformant': eligible}
    monkeypatch.setattr(pilot.generation, 'run_cell', fake_call)
    def fake_stage(source, public, destination):
        destination.mkdir()
        return {'test_staging': True}
    monkeypatch.setattr(pilot, 'stage_fixtures', fake_stage)
    return calls


def test_failed_answer_does_not_trigger_another_call_on_resume(tmp_path, monkeypatch):
    calls = install_fake_preparation(monkeypatch, tmp_path, False)
    def forbidden(*args, **kwargs): raise AssertionError('No execution for invalid generation')
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    assert pilot.main(['--resume', str(tmp_path)]) == 0
    assert pilot.main(['--resume', str(tmp_path)]) == 0
    assert len(calls) == 1
    record = pilot.replay.read_json(tmp_path / 'run.json')
    assert {r['state'] for r in record['conditions'].values()} == {'generation_not_eligible'}


def test_identical_assembly_explicitly_reuses_raw_execution(tmp_path, monkeypatch):
    calls = install_fake_preparation(monkeypatch, tmp_path, True)
    executions = []
    def fake_condition(*args):
        executions.append(1)
        return {'state': 'evaluated', 'evaluated': True, 'positive_passes': 6, 'correct_rejections': 3,
                'assembly': {'state': 'not_applied', 'operations': []}, 'profile_all_controls_pass': True}
    monkeypatch.setattr(pilot, 'run_condition', fake_condition)
    monkeypatch.setattr(pilot.binding_assembly, 'assemble', lambda value, *args: (copy.deepcopy(value), {'state': 'unchanged', 'operations': []}))
    assert pilot.main(['--resume', str(tmp_path)]) == 0
    run = pilot.replay.read_json(tmp_path / 'run.json')
    assert len(calls) == len(executions) == 1
    assert run['conditions']['assembled']['execution_reused_from'] == 'raw'


def test_dry_run_never_calls_model_or_executor(monkeypatch, capsys):
    design = {'case': 'extension/unit', 'conditions': ['raw', 'assembled']}
    prepared = (design, 'unit', model(), None, {}, {}, {}, None, {}, {}, {}, None,
                {'messages': [{'content': 'public'}]}, {'x': 'sha'})
    monkeypatch.setattr(pilot, 'prepare', lambda *args: prepared)
    def forbidden(*args, **kwargs): raise AssertionError('Offline preflight only')
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    assert pilot.main(['--dry-run']) == 0
    assert '"maximum_inference_requests": 1' in capsys.readouterr().out


def test_fixture_bank_uses_exact_public_nominal_bytes_but_preserves_other_variants(tmp_path):
    public = tmp_path / 'public'
    old = tmp_path / 'controls'
    public.mkdir()
    (old / 'scenarios/nominal').mkdir(parents=True)
    (old / 'scenarios/changed').mkdir(parents=True)
    (public / 'data.jsonl').write_text('{"x":1,"y":2}\n')
    (old / 'scenarios/nominal/data.jsonl').write_text('{"x": 1, "y": 2}\n')
    (old / 'scenarios/changed/data.jsonl').write_text('{"x":3,"y":2}\n')
    destination = tmp_path / 'new_bank'
    receipt = pilot.stage_fixtures(old, public, destination)
    assert len(receipt['serialization_differences']) == 1
    assert (destination / 'scenarios/nominal/data.jsonl').read_bytes() == (public / 'data.jsonl').read_bytes()
    assert (destination / 'scenarios/changed/data.jsonl').read_bytes() == (old / 'scenarios/changed/data.jsonl').read_bytes()


@pytest.mark.parametrize('changed', ['{"x":2}', '{"x":true}', '{"x":1.0}'])
def test_nominal_value_or_scalar_type_changes_stop_before_inference(changed, tmp_path):
    public, old = tmp_path / 'public', tmp_path / 'old'
    public.mkdir(); old.mkdir()
    (public / 'data.json').write_text('{"x":1}')
    (old / 'data.json').write_text(changed)
    with pytest.raises(ValueError): pilot.nominal_alignment(public, old)
