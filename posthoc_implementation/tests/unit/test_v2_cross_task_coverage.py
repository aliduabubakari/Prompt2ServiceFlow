"""Coverage must not turn names, reused data or prior model success into proof."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_cross_task_coverage as audit

analysis = audit.analysis


def backends():
    return {'window': {'services': {('a', '1.0.0'), ('b', '1.0.0')}, 'exact_roster': True, 'method_route': True},
            'csv': {'services': {('csv', '1.0.0')}, 'exact_roster': False, 'method_route': False}}


def bindings(*names): return [{'service_id': n, 'service_version': '1.0.0'} for n in names]


def classify(items=None, *, review=None, inputs=None, profile=None):
    return analysis.classify('main/example', bindings('a', 'b') if items is None else items, backends(),
        inputs or {'findings': [], 'inputs': []}, review, profile or {'state': 'no_task_profile_registered', 'findings': []})


def test_matching_roster_does_not_establish_task_semantics_or_authorize_generation():
    row = classify()
    assert row['complete_backend_rosters'] == ['window']
    assert row['state'] == 'public_semantics_and_profile_review_required'
    assert row['original_task_semantics'] == 'not_certified'
    assert row['new_generation_ready'] is False and row['semantic_success'] is None


def test_cannot_drop_missing_transformer_or_merge_independent_backends():
    row = classify(bindings('a', 'b', 'alignment'))
    assert row['state'] == 'unsupported_operations' and row['missing_services'] == ['alignment@1.0.0']
    row = classify(bindings('a', 'b', 'csv'))
    assert row['state'] == 'cross_backend_or_roster_composition_unverified'


def test_wrong_version_and_duplicate_required_operations_do_not_count_as_covered():
    wrong = bindings('a', 'b'); wrong[0]['service_version'] = '2.0.0'
    assert classify(wrong)['missing_services'] == ['a@2.0.0']
    assert classify(bindings('a', 'b', 'a'))['complete_backend_rosters'] == []


def test_csv_mechanism_and_existing_clarified_case_are_not_full_original_tasks():
    assert classify(bindings('csv'))['state'] == 'mechanism_only_no_ir_method_route'
    review = {'existing_development_case': True, 'full_original_task_intent_certified': False,
              'scope': 'Different explicit development semantics'}
    row = classify(review=review, profile={'state': 'structural_profile_match', 'findings': []})
    assert row['state'] == 'clarified_development_scope_only'
    assert row['original_task_semantics'] == 'clarified_or_partial' and row['new_generation_ready'] is False


def test_three_ingestions_do_not_make_two_public_sources_sufficient():
    backend = {'relational': {'services': {('a', '1.0.0'), ('b', '1.0.0')}, 'exact_roster': True, 'method_route': True}}
    row = analysis.classify('extension/example', bindings('a', 'b'), backend,
        {'findings': [], 'inputs': [{'role': 'primary'}, {'role': 'secondary'}]}, None, {'findings': []})
    assert row['state'] == 'public_input_contract_review_required'
    assert 'three_source_runtime_requires_three_explicit_public_source_roles' in row['input_findings']


def public_inputs(tmp_path, manifest):
    workspace = tmp_path / 'workspace'; root = workspace / 'fixtures/scenarios/nominal'; root.mkdir(parents=True)
    (root / 'fixture.json').write_text(json.dumps(manifest))
    return workspace, root


def test_named_missing_input_and_remote_resource_are_reported_without_fetching(tmp_path):
    workspace, _ = public_inputs(tmp_path, {'inputs': {'one': 'missing.csv', 'two': 'https://example.invalid/data.json'}})
    r = analysis.input_inventory(workspace, 1024)
    assert 'missing_named_source:one' in r['findings']
    assert 'nonlocal_or_unresolved_source:two' in r['findings']


@pytest.mark.parametrize('escape', ['../outside.json', '/outside.json'])
def test_manifest_path_escape_is_rejected(tmp_path, escape):
    workspace, _ = public_inputs(tmp_path, {'inputs': {'one': escape}})
    with pytest.raises(ValueError, match='escapes'): analysis.input_inventory(workspace, 1024)


def test_symlink_escape_is_rejected(tmp_path):
    workspace, root = public_inputs(tmp_path, {'inputs': {'one': 'alias.json'}})
    other = tmp_path / 'outside.json'; other.write_text('{}')
    (root / 'alias.json').symlink_to(other)
    with pytest.raises(ValueError, match='escapes'): analysis.input_inventory(workspace, 1024)


def test_absent_manifest_is_unmapped_not_proof_that_all_input_data_is_absent(tmp_path):
    workspace = tmp_path / 'workspace'; inputs = workspace / 'fixtures/inputs'; inputs.mkdir(parents=True)
    (inputs / 'real.csv').write_text('x\n1\n')
    r = analysis.input_inventory(workspace, 1024)
    assert r['state'] == 'public_files_without_manifest_mapping'
    assert r['unmapped_public_input_files'] == ['fixtures/inputs/real.csv']


def test_explicit_profile_role_cannot_be_inferred_from_a_similar_source_name():
    review = {'backend': 'window', 'profile_file': 'reviewed.json'}
    profile = {'input_keys': {'records': 'readings', 'registry': 'buildings'},
        'fields': {'entity': 'e', 'group': 'g', 'time': 't', 'energy': 'k', 'demand': 'd', 'quality': 'q', 'capacity': 'c'}}
    data = {'inputs': [{'role': 'similar_readings', 'shape': 'records', 'fields': ['e', 'g', 't', 'k', 'd', 'q']}],
            'manifest': {}}
    before = copy.deepcopy(data)
    result = analysis.profile_checks(data, review, lambda name: profile)
    assert 'missing_explicit_profile_role:readings' in result['findings']
    assert data == before


def test_review_queue_ignores_model_results_and_excludes_development_cases():
    one = classify(bindings('a', 'b', 'missing')); one['case'] = 'main/one'
    two = classify(); two['case'] = 'main/two'
    development = classify(review={'existing_development_case': True}); development['case'] = 'main/developed'
    rows = [one, two, development]
    first = analysis.summarize(rows)
    for row in rows: row['model_success_rate'] = 1.0 if row['case'] == 'main/one' else 0
    second = analysis.summarize(rows)
    assert first == second
    assert [r['case'] for r in first['review_queue']] == ['main/two', 'main/one']
    assert first['new_generation_ready'] == 0 and first['llm_calls'] == first['workflow_executions'] == 0


def test_registry_inspection_does_not_execute_values(tmp_path):
    path = tmp_path / 'registry.py'
    path.write_text("OPERATIONS = {'safe_service': should_never_run()}\n")
    assert analysis.registry_keys(path, 'OPERATIONS') == ['safe_service']


def test_real_registries_have_exact_expected_service_counts():
    registered = audit.registered_backends()
    assert {k: len(v['services']) for k, v in registered.items()} == {
        'window': 6, 'relational': 7, 'csv_mechanism': 3, 'isolated_port_helpers': 3}
    assert len({k for value in registered.values() for k in value['services']}) == 17


def test_new_planning_inventory_exclusions_are_explicit_and_restored(monkeypatch):
    tool = ROOT / 'audit/v2/fusion_public_tools_v2_3.py'
    def inventory(): return [*audit.ENTRY_POINTS, tool]
    monkeypatch.setattr(audit.frozen.runner, 'implementation_files', inventory)
    def delegated():
        assert audit.frozen.runner.implementation_files() == [tool]
        return {'verified': True}
    monkeypatch.setattr(audit.anchor, 'prepare', delegated)
    assert audit.prepare_anchor() == {'verified': True}
    assert audit.frozen.runner.implementation_files is inventory
