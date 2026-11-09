"""Offline guards for a model-authored patch; no automatic graph or input fixes."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_contract_repair as pilot


def document():
    return {'source': {'fixed': 'public'}, 'requirement': {'fixed': 'task'},
            'artifacts': [{'artifact_id': 'shared', 'producer': 'read'}],
            'control_flow': {'edges': []},
            'service_intents': [{'intent_id': 'read', 'inputs': [], 'outputs': ['shared'], 'capability': 'Keep intent'}],
            'bindings': [{'intent_id': 'read', 'service_id': 'fixed_service', 'service_version': '1.0.0',
                          'input_bindings': [], 'output_bindings': [{'port': 'out', 'artifact_id': 'shared'}],
                          'parameter_bindings': {'operation_profile': 'fixed_profile'}}],
            'policies': {'fixed': True}, 'runtime': {'fixed': True}}


def response():
    return {'patch': [{'op': 'replace', 'path': '/artifacts',
                       'value': [{'artifact_id': 'new_output', 'producer': 'read'}]},
                      {'op': 'replace', 'path': '/service_intents/0/outputs', 'value': ['new_output']},
                      {'op': 'replace', 'path': '/bindings/0/output_bindings',
                       'value': [{'port': 'out', 'artifact_id': 'new_output'}]}],
            'unresolved_requirements': ['Source mapping is not specified.']}


def config():
    return {'model_name': 'unit', 'base_url': 'http://localhost:1234/v1', 'api_key_env': 'UNIT_TOKEN',
            'max_tokens': 4096, 'temperature': .2, 'top_p': 1, 'seed': 101, 'request_timeout_s': 30}


def payload(text, finish='stop', **message_fields):
    return {'status': 'response_received', 'latency_s': 1, 'response': {'model': 'unit',
            'choices': [{'finish_reason': finish, 'message': {'role': 'assistant', 'content': text, **message_fields}}],
            'usage': {'completion_tokens': 123}}}


def test_only_the_model_patch_is_applied_and_protected_decisions_are_unchanged():
    doc = document()
    old = copy.deepcopy(doc)
    changed = pilot.apply_response(doc, response())
    assert doc == old
    assert changed['artifacts'][0]['artifact_id'] == 'new_output'
    for field in ('source', 'requirement', 'policies', 'runtime'):
        assert changed[field] == old[field]
    assert changed['bindings'][0]['service_id'] == 'fixed_service'
    assert changed['bindings'][0]['parameter_bindings'] == old['bindings'][0]['parameter_bindings']
    assert changed['service_intents'][0]['capability'] == 'Keep intent'


@pytest.mark.parametrize('path', [
    '/source', '/runtime', '/policies', '/bindings', '/bindings/0', '/bindings/0/service_id',
    '/bindings/0/parameter_bindings', '/service_intents', '/service_intents/0/intent_id',
    '/artifacts/0/fixture_ref', '/bindings/1/input_bindings'])
def test_patch_cannot_edit_protected_or_unlisted_paths(path):
    answer = response()
    answer['patch'] = [{'op': 'replace', 'path': path, 'value': []}]
    with pytest.raises(Exception): pilot.apply_response(document(), answer)


@pytest.mark.parametrize('mutation', ['duplicate', 'add', 'extra', 'no_uncertainty', 'not_array'])
def test_rejects_ambiguous_or_malformed_patch_structure(mutation):
    answer = response()
    if mutation == 'duplicate': answer['patch'] = answer['patch'][:1] * 2
    if mutation == 'add': answer['patch'][0]['op'] = 'add'
    if mutation == 'extra': answer['patch'][0]['extra'] = 'not allowed'
    if mutation == 'no_uncertainty': del answer['unresolved_requirements']
    if mutation == 'not_array': answer['patch'] = {}
    with pytest.raises(Exception): pilot.apply_response(document(), answer)


def test_does_not_repair_a_schema_invalid_model_patch_automatically():
    answer = response()
    answer['patch'][0]['value'] = 'not an artifact array'
    schema = {'type': 'object', 'properties': {'artifacts': {'type': 'array'}}}
    row, saved, candidate = pilot.assess(payload(json.dumps(answer)), document(), schema)
    assert row['status'] == 'patch_schema_error'
    assert candidate['artifacts'] == 'not an artifact array'
    assert saved == answer
    assert row['semantic_outcome'] == 'not_measured'


def test_model_uncertainties_are_retained_even_when_schema_passes():
    row, answer, _ = pilot.assess(payload(json.dumps(response())), document(), {'type': 'object'})
    assert row['status'] == 'schema_conformant_patch'
    assert row['unresolved_requirements'] == answer['unresolved_requirements']
    assert row['public_gates'] == 'not_remeasured'


@pytest.mark.parametrize('finish,text,fields', [
    ('length', json.dumps(response()), {}),
    ('stop', '', {'reasoning': json.dumps(response())}),
    ('tool_calls', '', {'tool_calls': [{'id': 'not executed'}]})])
def test_never_promotes_reasoning_tools_or_length_stopped_output(finish, text, fields):
    row, answer, candidate = pilot.assess(payload(text, finish, **fields), document(), {})
    assert row['patch_applied'] is False
    assert answer is candidate is None


def test_original_public_context_is_preserved_and_no_replacement_is_selected():
    user = {'role': 'user', 'content': 'complete original public task/catalog/schema'}
    old = copy.deepcopy(user)
    request = pilot.build_request(config(), user, document(), {}, {'checked': 'public'}, 'general rules')
    assert user == old
    assert request['messages'][1] == user
    assert json.loads(request['messages'][2]['content']) == document()
    assert request['max_tokens'] == 4096
    assert request['seed'] == 101
    assert 'unresolved_requirements' in request['messages'][-1]['content']


def test_no_static_findings_still_does_not_make_execution_ready(monkeypatch):
    monkeypatch.setattr(pilot.audit, 'inspect', lambda *args: {'external_inputs': [], 'findings': [], 'finding_counts': {}})
    doc = document()
    checked = pilot.inspect_candidate(doc, {}, None, {}, {'files': []})
    assert checked['execution_ready'] is False
    assert checked['semantic_outcome'] == 'not_measured'


def test_dispatch_unknown_is_never_repeated(tmp_path):
    (tmp_path / 'dispatched.json').write_text('{}')
    def forbidden(**kwargs): raise AssertionError('No second request')
    row = pilot.execute(tmp_path, {}, config(), 'unit-secret', document(), {}, None, {}, {}, forbidden)
    assert row['status'] == 'interrupted_outcome_unknown'


def test_saved_response_is_reused_and_future_inspection_is_offline(tmp_path, monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def create(self, **kwargs):
            calls.append(kwargs)
            return payload(json.dumps(response()))['response']
    monkeypatch.setattr(pilot, 'inspect_candidate', lambda *args: {
        'analysis': {'findings': [], 'finding_counts': {}}, 'unresolved_bound_input_links': [],
        'context': {'artifact_fixture_links': [], 'multiple_writer_artifacts': {}}})
    args = (tmp_path, {'model': 'unit'}, config(), 'unit-secret', document(), {'type': 'object'}, None, {}, {}, Client)
    first = pilot.execute(*args)
    second = pilot.execute(*args)
    assert first == second
    assert len(calls) == 1
    assert first['execution_ready'] is False


def test_unavailable_input_links_and_unimplemented_merges_remain_visible(monkeypatch):
    analysis = {'external_inputs': [{'artifact_id': 'a', 'state': 'no_resolved_public_file'}],
                'findings': [], 'finding_counts': {}}
    monkeypatch.setattr(pilot.audit, 'inspect', lambda *args: analysis)
    doc = document()
    doc['bindings'].append({**copy.deepcopy(doc['bindings'][0]), 'intent_id': 'other'})
    inspected = pilot.inspect_candidate(doc, {}, None, {}, {'files': []})
    assert inspected['multi_writer_artifacts_need_registered_merge'] is True
    assert len(inspected['unresolved_bound_input_links']) == 1
    assert inspected['execution_ready'] is False
