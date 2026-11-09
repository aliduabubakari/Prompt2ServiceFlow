"""Strict compiler/registry controls; no inference or workflow runs in preparation."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_integration as pilot

spec = importlib.util.spec_from_file_location('previous_window_tests', ROOT / 'tests/unit/test_v2_paired_window.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)


def profile(): return pilot.replay.read_json(ROOT / 'audit/v2/runtime_profiles/bounded-window-1.json')
def ir(): return previous.ir()
def schema(): return previous.schema()


def test_exact_registry_dispatch_preserves_original_values():
    value, p = ir(), profile()
    old, old_profile = copy.deepcopy(value), copy.deepcopy(p)
    plan = pilot.backend.compile_plan(value, p)
    assert value == old and p == old_profile
    assert plan['strict_labels_verified'] is True
    assert plan['label_replacements'] == []
    assert plan['mock_fallback'] is False
    assert len(plan['order']) == 6


@pytest.mark.parametrize('mutation', [
    'unknown_service', 'unknown_version', 'unknown_label', 'unknown_parameter', 'streaming', 'branch',
    'intent_list', 'consumers', 'missing_link', 'scenario_specific_link', 'unsafe_link',
    'nonjson_input', 'wrong_writer', 'table_bundle'])
def test_unsupported_or_inconsistent_decisions_are_not_repaired(mutation):
    value = ir()
    b = value['bindings'][0]
    inputs = {a['artifact_id']: a for a in value['artifacts']}
    external = inputs[b['input_bindings'][0]['artifact_id']]
    if mutation == 'unknown_service': b['service_id'] = 'unknown'
    if mutation == 'unknown_version': b['service_version'] = '2.0.0'
    if mutation == 'unknown_label': b['parameter_bindings']['operation_profile'] = 'invented_label'
    if mutation == 'unknown_parameter': b['parameter_bindings']['extra_semantics'] = True
    if mutation == 'streaming': b['parameter_bindings']['modality_policy'] = {'true_streaming': True}
    if mutation == 'branch': value['control_flow']['branches'] = [{'unimplemented': True}]
    if mutation == 'intent_list': value['service_intents'][0]['outputs'] = []
    if mutation == 'consumers': external['consumers'] = []
    if mutation == 'missing_link': external.pop('fixture_ref', None)
    if mutation == 'scenario_specific_link': external['fixture_ref'] = 'fixtures/scenarios/nominal/fixture.json'
    if mutation == 'unsafe_link': external['fixture_ref'] = 'fixtures/inputs/../secret.json'
    if mutation == 'nonjson_input': external['fixture_ref'] = 'fixtures/inputs/file.csv'
    if mutation == 'wrong_writer': inputs[b['output_bindings'][0]['artifact_id']]['producer'] = 'wrong'
    if mutation == 'table_bundle': inputs[b['output_bindings'][0]['artifact_id']]['data_type'] = 'table'
    original = copy.deepcopy(value)
    with pytest.raises((ValueError, KeyError)): pilot.backend.compile_plan(value, profile())
    assert value == original


@pytest.mark.parametrize('mutation', ['version', 'rules', 'empty_field', 'pipeline_switch'])
def test_profile_is_explicit_and_does_not_dispatch_by_pipeline_name(mutation):
    p = profile()
    if mutation == 'version': p['profile_version'] = 'not_registered'
    if mutation == 'rules': p['rules']['energy'] = 'unknown'
    if mutation == 'empty_field': p['fields']['energy'] = ''
    if mutation == 'pipeline_switch': p['case'] = 'a_pipeline_name'
    with pytest.raises(ValueError): pilot.backend.compile_plan(ir(), p)


def scenarios():
    return [{'name': 'nominal', 'parameters': {}, 'fixture_root': 'fixtures/scenarios/nominal'}]


def test_package_export_uses_only_registered_real_entrypoint_and_preserves_inputs(tmp_path):
    value = ir()
    old = copy.deepcopy(value)
    destination = tmp_path / 'new_package'
    manifest = pilot.backend.materialize_runtime(value, profile(), scenarios(), destination, schema())
    assert value == old
    assert manifest['scenarios'] == scenarios()
    assert (destination / 'runtime/manifest.yaml').is_file()
    assert (destination / 'runtime/scripts/semantic_backend.py').is_file()
    entry = (destination / 'runtime/scripts/workflow.py').read_text()
    assert 'from semantic_backend import execute' in entry
    assert not (destination / 'artifacts').exists()
    receipt = json.loads((destination / 'runtime/scripts/compile_receipt.json').read_text())
    assert receipt['mock_fallback'] is False


def test_existing_package_is_never_overwritten(tmp_path):
    marker = tmp_path / 'keep.txt'
    marker.write_text('untouched')
    with pytest.raises(ValueError): pilot.backend.materialize_runtime(ir(), profile(), scenarios(), tmp_path, schema())
    assert marker.read_text() == 'untouched'


def test_unknown_label_stops_before_any_package_is_written(tmp_path):
    value = ir()
    value['bindings'][0]['parameter_bindings']['operation_profile'] = 'unresolved'
    destination = tmp_path / 'not_written'
    with pytest.raises(ValueError): pilot.backend.materialize_runtime(value, profile(), scenarios(), destination, schema())
    assert not destination.exists()


@pytest.mark.parametrize('mutation', ['parameter', 'duplicate', 'unsafe_root'])
def test_scenario_contract_does_not_ignore_unsupported_parameters(mutation, tmp_path):
    s = scenarios()
    if mutation == 'parameter': s[0]['parameters'] = {'hidden_threshold': 2}
    if mutation == 'duplicate': s.append(copy.deepcopy(s[0]))
    if mutation == 'unsafe_root': s[0]['fixture_root'] = '../outside'
    destination = tmp_path / 'not_written'
    with pytest.raises(ValueError): pilot.backend.materialize_runtime(ir(), profile(), s, destination, schema())
    assert not destination.exists()


def test_runtime_receipt_identifies_exact_profile_without_calling_a_mock(tmp_path, monkeypatch):
    value, p = ir(), profile()
    monkeypatch.setattr(pilot.backend.window, 'execute', lambda *args: {'workflow_status': 'completed', 'events': [], 'states': {}})
    result = pilot.backend.execute(value, p, tmp_path, tmp_path)
    receipt = json.loads((tmp_path / 'logs/semantic_backend_receipt.json').read_text())
    assert receipt['ir_sha256'] == pilot.backend.digest(value)
    assert receipt['profile_sha256'] == pilot.backend.digest(p)
    assert receipt['mock_fallback'] is False and receipt['label_replacements'] == []
    assert result['semantic_backend'] == receipt


def test_business_pass_without_real_backend_receipt_fails_integration(monkeypatch):
    monkeypatch.setattr(pilot.prior, 'neutral_check', lambda *args: {'pass': True, 'checks': []})
    result = {'scenario': 'nominal', '_snapshot': {}, '_errors': []}
    checked = pilot.evaluate(result, ir(), None, profile(), {'positive_scenarios': ['nominal']})
    assert checked['pass'] is False


def test_dry_run_makes_no_model_or_runtime_call(monkeypatch, capsys):
    monkeypatch.setattr(pilot, 'prepare', lambda: (
        {'positive_scenarios': ['nominal'], 'rejection_scenarios': ['bad']}, {}, profile(), None, {}, {}, {}, {'x': 'sha'}))
    def forbidden(*args, **kwargs): raise AssertionError('No actual workflow execution during preparation')
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.subprocess, 'run', forbidden)
    assert pilot.main(['--dry-run']) == 0
    text = capsys.readouterr().out
    assert '"mock_fallback": false' in text and '"api_requests": 0' in text


def test_reference_control_metadata_projection_preserves_every_business_decision(tmp_path):
    workspace = tmp_path / 'public'
    (workspace / 'catalog').mkdir(parents=True)
    original = ir()
    references = list(dict.fromkeys(ref for intent in original['service_intents'] for ref in intent['source_step_refs']))
    task = '\n'.join(f'{n}. {reference} - Public step\n  - Objective: Perform the declared public task step.'
                     for n, reference in enumerate(references, 1))
    (workspace / 'task.md').write_text(task)
    (workspace / 'catalog/catalog.yaml').write_text('version: 0.3.2\n')
    task_sha = pilot.controls.sha256(workspace / 'task.md')
    catalog_sha = pilot.controls.sha256(workspace / 'catalog/catalog.yaml')
    reference_source = ir()['source']
    manifest = {'files': [{'path': 'task.md', 'sha256': task_sha},
                          {'path': 'catalog/catalog.yaml', 'sha256': catalog_sha}],
                'task': {'description_sha256': task_sha},
                'catalog': {'version': '0.3.2', 'sanitized_catalog_yaml_sha256': catalog_sha},
                'instance': {'split': reference_source['split'], 'id': reference_source['pipeline_id'],
                             'benchmark_id': reference_source['benchmark_id']}}
    (workspace / 'workspace.yaml').write_text(pilot.controls.yaml.safe_dump(manifest))
    old = copy.deepcopy(original)
    public, edits = pilot.public_control_view(original, workspace)
    assert original == old
    assert edits and all(edit['path'].lstrip('/') in pilot.generation.compact_ir.BOOKKEEPING or
                         edit['path'].endswith('/evidence') for edit in edits)
    assert public['source']['description_path'] == 'task.md'
    assert 'internal_spec_path' not in public['source']
    for key in old:
        if key not in (*pilot.generation.compact_ir.BOOKKEEPING, 'service_intents'):
            assert old[key] == public[key]
    for before, after in zip(old['service_intents'], public['service_intents']):
        assert {k: v for k, v in before.items() if k != 'evidence'} == {k: v for k, v in after.items() if k != 'evidence'}
        assert all(e['source'] == 'description' and e['text'] in task for e in after['evidence'])
    # Match the stricter model-visible schema rather than the root reference
    # schema which intentionally retains the private provenance extensions.
    public_schema = schema()
    for key in ('internal_spec_path', 'internal_spec_sha256'):
        public_schema['properties']['source']['properties'].pop(key, None)
    from jsonschema import Draft202012Validator
    Draft202012Validator(public_schema).validate(public)
    wrong = copy.deepcopy(original)
    wrong['source']['pipeline_id'] = 'different_case'
    with pytest.raises(ValueError): pilot.public_control_view(wrong, workspace)
    missing = copy.deepcopy(original)
    missing['service_intents'][0]['source_step_refs'] = ['absent_public_step']
    with pytest.raises(ValueError): pilot.public_control_view(missing, workspace)
