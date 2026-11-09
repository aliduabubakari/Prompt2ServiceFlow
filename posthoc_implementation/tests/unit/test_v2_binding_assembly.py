"""Assembly controls: preserve business decisions, refuse ambiguous reconstruction."""
import copy
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_binding_assembly as pilot


def policy(): return json.loads(pilot.POLICY.read_text())


def descriptor():
    return {'interface': {
        'inputs': [{'name': 'input', 'channel': 'artifact', 'data_type': 'csv', 'cardinality': 'one'}],
        'outputs': [{'name': 'data', 'required': True, 'channel': 'artifact', 'data_type': 'json', 'cardinality': 'one'},
                    {'name': 'report', 'required': True, 'channel': 'artifact', 'data_type': 'status', 'cardinality': 'one'}]}}


def get_catalog(service, version): return descriptor(), None


def document():
    return {'source': {'preserve': 'public'}, 'control_flow': {'edges': []},
        'artifacts': [{'artifact_id': 'input_data', 'producer': None, 'fixture_ref': 'fixtures/inputs/data.csv'},
                      {'artifact_id': 'business_data', 'producer': 'step', 'role': 'output'}],
        'service_intents': [{'intent_id': 'step', 'inputs': ['stale_input'], 'outputs': ['stale_output'],
                             'capability': 'Preserve this business intent'}],
        'bindings': [{'intent_id': 'step', 'service_id': 'service', 'service_version': '1.0.0',
                      'parameter_bindings': {'operation_profile': 'model_authored'},
                      'input_bindings': [{'port': 'input', 'artifact_id': 'input_data'}],
                      'output_bindings': [{'port': 'data', 'artifact_id': 'business_data'},
                                          {'port': 'report', 'artifact_id': 'model_chosen_report'}]}],
        'policies': {'keep': True}, 'runtime': {'keep': True}}


def test_status_declaration_and_projection_preserve_business_decisions():
    source = document()
    old = copy.deepcopy(source)
    candidate, decision = pilot.binding_assembly.assemble(source, get_catalog, policy())
    assert source == old
    assert decision['state'] == 'assembled'
    assert len(decision['operations']) == 3
    assert candidate['bindings'] == source['bindings']
    assert candidate['artifacts'][:2] == source['artifacts']
    report = candidate['artifacts'][-1]
    assert report['artifact_id'] == 'model_chosen_report'
    assert report['producer'] == 'step' and report['consumers'] == []
    assert report['role'] == report['data_type'] == 'status'
    assert 'value' not in report and 'content' not in report
    assert candidate['service_intents'][0]['inputs'] == ['input_data']
    assert candidate['service_intents'][0]['outputs'] == ['business_data', 'model_chosen_report']
    assert candidate['source'] == source['source']
    pilot.binding_assembly.verify_preservation(source, candidate)


def test_second_assembly_is_idempotent():
    first, _ = pilot.binding_assembly.assemble(document(), get_catalog, policy())
    second, decision = pilot.binding_assembly.assemble(first, get_catalog, policy())
    assert second == first
    assert decision['state'] == 'unchanged'
    assert not decision['operations']


@pytest.mark.parametrize('mutation', ['optional', 'parameter', 'non_status', 'many'])
def test_only_required_single_artifact_status_outputs_can_be_declared(mutation):
    d = descriptor()
    report = d['interface']['outputs'][1]
    if mutation == 'optional': report['required'] = False
    if mutation == 'parameter': report['channel'] = 'parameter'
    if mutation == 'non_status': report['data_type'] = 'json'
    if mutation == 'many': report['cardinality'] = 'many'
    source = document()
    candidate, decision = pilot.binding_assembly.assemble(source, lambda *args: (d, None), policy())
    assert candidate == source
    assert decision['state'] == 'blocked_no_changes'
    assert not decision['operations']


@pytest.mark.parametrize('mutation', ['bound_input', 'intent_input'])
def test_a_consumed_missing_report_cannot_be_filled_as_unused_scaffolding(mutation):
    source = document()
    if mutation == 'bound_input':
        source['bindings'][0]['input_bindings'] = [{'port': 'input', 'artifact_id': 'model_chosen_report'}]
    else:
        source['service_intents'][0]['inputs'] = ['model_chosen_report']
    candidate, decision = pilot.binding_assembly.assemble(source, get_catalog, policy())
    assert candidate == source
    assert decision['state'] == 'blocked_no_changes'


@pytest.mark.parametrize('mutation', ['missing_business_output', 'missing_input', 'duplicate_artifact',
                                     'duplicate_binding', 'duplicate_intent', 'multiple_writers', 'unknown_port', 'roster'])
def test_never_infers_missing_business_decisions_or_repairs_ambiguous_rosters(mutation):
    source = document()
    if mutation == 'missing_business_output': source['artifacts'].pop()
    if mutation == 'missing_input': source['artifacts'].pop(0)
    if mutation == 'duplicate_artifact': source['artifacts'].append(copy.deepcopy(source['artifacts'][0]))
    if mutation == 'duplicate_binding': source['bindings'].append(copy.deepcopy(source['bindings'][0]))
    if mutation == 'duplicate_intent': source['service_intents'].append(copy.deepcopy(source['service_intents'][0]))
    if mutation == 'multiple_writers': source['bindings'][0]['output_bindings'].append({'port': 'report', 'artifact_id': 'business_data'})
    if mutation == 'unknown_port': source['bindings'][0]['output_bindings'][0]['port'] = 'invented'
    if mutation == 'roster': source['service_intents'][0]['intent_id'] = 'other'
    old = copy.deepcopy(source)
    candidate, decision = pilot.binding_assembly.assemble(source, get_catalog, policy())
    assert source == candidate == old
    assert decision['state'] == 'blocked_no_changes'
    assert decision['operations'] == []


def test_failure_after_an_eligible_addition_discards_all_changes():
    source = document()
    source['bindings'][0]['output_bindings'].reverse()
    source['bindings'][0]['output_bindings'].append({'port': 'invented', 'artifact_id': 'other'})
    candidate, decision = pilot.binding_assembly.assemble(source, get_catalog, policy())
    assert candidate == source
    assert not decision['operations']


def test_existing_status_artifacts_are_not_retyped_or_reassigned():
    source = document()
    source['artifacts'].append({'artifact_id': 'model_chosen_report', 'producer': 'step', 'role': 'output', 'data_type': 'any'})
    candidate, _ = pilot.binding_assembly.assemble(source, get_catalog, policy())
    assert candidate['artifacts'] == source['artifacts']


def test_unavailable_public_descriptor_blocks_without_changes():
    source = document()
    candidate, decision = pilot.binding_assembly.assemble(source, lambda *args: (None, 'missing'), policy())
    assert candidate == source
    assert decision['state'] == 'blocked_no_changes'


@pytest.mark.parametrize('field', ['bindings', 'control_flow', 'policies', 'runtime', 'source'])
def test_preservation_check_detects_mutation_of_protected_fields(field):
    before = document()
    after = copy.deepcopy(before)
    after[field] = []
    with pytest.raises(ValueError): pilot.binding_assembly.verify_preservation(before, after)


def test_preservation_check_detects_rewritten_business_artifact():
    before = document()
    after = copy.deepcopy(before)
    after['artifacts'][0]['fixture_ref'] = 'fixtures/invented.csv'
    with pytest.raises(ValueError): pilot.binding_assembly.verify_preservation(before, after)


def test_zero_bound_inputs_is_unknown_coverage_not_a_pass():
    inspection = {'analysis': {'external_inputs': []}, 'unresolved_bound_input_links': [],
                  'context': {'artifact_fixture_links': []}}
    result = pilot.input_readiness(inspection)
    assert result['resolved_bound_input_fraction'] is None
    assert result['state'] == 'not_established_no_bound_external_inputs'


def test_resolved_files_are_not_a_semantic_or_source_role_pass():
    inspection = {'analysis': {'external_inputs': [{}, {}]}, 'unresolved_bound_input_links': [],
                  'context': {'artifact_fixture_links': [{}]}}
    result = pilot.input_readiness(inspection)
    assert result['resolved_bound_input_fraction'] == 1
    assert result['state'] == 'bound_files_resolved_roles_not_verified'


def test_dry_run_has_no_api_or_workflow_execution(monkeypatch, capsys):
    source = document()
    previous = {'case': 'main/unit', 'model_id': 'unit'}
    monkeypatch.setattr(pilot, 'prepare', lambda: ({}, previous, source, {}, None, {}, {}, policy(), {'input': 'sha'}))
    monkeypatch.setattr(pilot.generation.census, 'Catalog', lambda: type('Catalog', (), {'get': lambda self, *args: get_catalog(*args[1:])})())
    def forbidden(*args, **kwargs): raise AssertionError('No API calls or execution')
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.subprocess, 'run', forbidden)
    assert pilot.main(['--dry-run']) == 0
    text = capsys.readouterr().out
    assert '"api_requests": 0' in text and '"workflow_executions": 0' in text
