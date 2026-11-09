"""Offline tests: schema feedback does not authorize unrelated edits or retries."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_enum_repair as pilot


def document():
    return {'ir_version': '0.1.0', 'composition_id': 'unit', 'catalog_snapshot': {}, 'source': {},
            'x/y~z': 'bad', 'items': [{'mode': 'bad'}], 'untouched': {'keep': ['original']}}


def schema():
    return {'type': 'object', 'properties': {'x/y~z': {'enum': ['yes', 'no']},
            'items': {'type': 'array', 'items': {'type': 'object', 'properties': {'mode': {'enum': ['one', 'two']}}}}}}


def metadata():
    d = document()
    return {k: d[k] for k in pilot.generation.compact_ir.BOOKKEEPING}


def patch():
    return [{'op': 'replace', 'path': '/x~1y~0z', 'value': 'yes'},
            {'op': 'replace', 'path': '/items/0/mode', 'value': 'one'}]


def payload(content, finish='stop', **fields):
    return {'status': 'response_received', 'latency_s': 1, 'response': {
        'choices': [{'finish_reason': finish, 'message': {'role': 'assistant', 'content': content, **fields}}],
        'usage': {'completion_tokens': 50}}}


def config():
    return {'model_name': 'unit', 'base_url': 'http://localhost:1234/v1', 'api_key_env': 'UNIT_TOKEN',
            'max_tokens': 1024, 'temperature': .2, 'top_p': 1, 'seed': 101, 'request_timeout_s': 30}


def test_schema_paths_are_escaped_and_model_patch_preserves_other_values():
    original = document()
    before = copy.deepcopy(original)
    sites = pilot.enum_sites(original, schema())
    assert set(sites) == {'/x~1y~0z', '/items/0/mode'}
    changed = pilot.apply_patch(original, patch(), sites)
    assert original == before
    assert changed['untouched'] == original['untouched']
    assert changed['items'][0]['mode'] == 'one'
    assert not pilot.errors(changed, schema())


@pytest.mark.parametrize('bad', [
    [{'op': 'replace', 'path': '/untouched', 'value': {}}],
    [{'op': 'add', 'path': '/x~1y~0z', 'value': 'yes'}],
    [{'op': 'remove', 'path': '/x~1y~0z'}],
    [{'op': 'replace', 'path': '/x~1y~0z', 'value': 'invented'}],
    [{'op': 'replace', 'path': '/x~1y~0z', 'value': 'yes', 'extra': True}],
    [{'op': 'replace', 'path': '/x~1y~0z', 'value': 'yes'}] * 2,
    [], {'op': 'replace', 'path': '/x~1y~0z', 'value': 'yes'}])
def test_rejects_unauthorized_patch(bad):
    d = document()
    with pytest.raises(Exception): pilot.apply_patch(d, bad, pilot.enum_sites(d, schema()))
    assert d == document()


def test_partial_repair_remains_schema_invalid():
    d = document()
    row, _, changed = pilot.assess(payload(json.dumps(patch()[:1])), d, schema(), pilot.enum_sites(d, schema()), metadata())
    assert row['status'] == 'remaining_schema_errors'
    assert row['schema_conformant'] is False
    assert len(row['schema_errors_after']) == 1
    assert changed['items'] == d['items']


def test_success_is_schema_only_and_metadata_is_unchanged():
    d = document()
    row, _, _ = pilot.assess(payload(json.dumps(patch())), d, schema(), pilot.enum_sites(d, schema()), metadata())
    assert row['status'] == 'schema_repaired'
    assert row['metadata_conformant'] is True
    assert row['semantic_outcome'] == 'not_measured'
    assert row['public_gates'] == 'not_remeasured'


@pytest.mark.parametrize('text', ['```json\n[]\n```', '[', '[{"op":"replace","op":"add"}]'])
def test_malformed_or_duplicate_key_output_is_not_repaired(text):
    d = document()
    row, model_patch, changed = pilot.assess(payload(text), d, schema(), pilot.enum_sites(d, schema()), metadata())
    assert row['status'] == 'rejected_patch'
    assert model_patch is changed is None


@pytest.mark.parametrize('finish,fields', [('length', {}), ('stop', {'reasoning': json.dumps(patch())}),
                                        ('tool_calls', {'tool_calls': [{'id': 'never_execute'}]})])
def test_never_uses_length_stopped_reasoning_or_tool_output(finish, fields):
    d = document()
    text = json.dumps(patch()) if finish == 'length' else ''
    row, _, candidate = pilot.assess(payload(text, finish, **fields), d, schema(), pilot.enum_sites(d, schema()), metadata())
    assert candidate is None
    assert row['patch_applied'] is False


def test_refuses_other_schema_error_types_or_no_error():
    with pytest.raises(ValueError): pilot.enum_sites({}, {'type': 'object', 'required': ['missing']})
    with pytest.raises(ValueError): pilot.enum_sites({'value': 'bad'}, {'type': 'object'})


def test_request_retains_public_context_and_records_new_output_budget():
    original = [{'role': 'system', 'content': 'old full-object instruction'}, {'role': 'user', 'content': 'public task/schema'}]
    before = copy.deepcopy(original)
    request = pilot.build_request(config(), original, 'saved original candidate', pilot.enum_sites(document(), schema()))
    assert original == before
    assert request['messages'][1] == original[1]
    assert request['messages'][2] == {'role': 'assistant', 'content': 'saved original candidate'}
    assert request['max_tokens'] == 1024
    assert request['seed'] == 101


def fake_factory(raw, calls):
    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def create(self, **request):
            calls.append((self.kwargs, request))
            return raw
    return Client


def test_saved_completion_is_reused_without_another_call(tmp_path):
    d = document()
    sites = pilot.enum_sites(d, schema())
    calls = []
    factory = fake_factory(payload(json.dumps(patch()))['response'], calls)
    args = (tmp_path, {'model': 'unit'}, config(), 'unit-secret', d, schema(), sites, metadata(), factory)
    first = pilot.execute(*args)
    second = pilot.execute(*args)
    assert len(calls) == 1
    assert calls[0][0]['max_retries'] == 0
    assert first == second
    assert first['status'] == 'schema_repaired'


def test_ambiguous_dispatch_is_never_repeated(tmp_path):
    (tmp_path / 'dispatched.json').write_text('{}')
    calls = []
    d = document()
    row = pilot.execute(tmp_path, {}, config(), 'unit-secret', d, schema(), pilot.enum_sites(d, schema()), metadata(), fake_factory({}, calls))
    assert row['status'] == 'interrupted_outcome_unknown'
    assert not calls
