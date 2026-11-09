"""Read-only analysis, conservative support, safety flags, and score-free ranking."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import plan_v2_corpus_replay as planner
analysis = planner.analysis


class Catalog:
    def get(self, workspace, service, version):
        if service == 'missing_catalog':
            return None, 'service_version_absent_from_public_catalog'
        return {'policies': {'network_access': 'forbidden', 'secret_access': 'forbidden'},
                'capability': {'summary': 'Local parse', 'operations': ['Read a CSV']},
                'interface': {'inputs': [{'name': 'csv_file', 'required': True}],
                              'outputs': [{'name': 'validated_dataset', 'required': True}],
                              'parameters': [{'name': 'output_path', 'required': True}]}}, None


def document(service='csv_tabular_schema_validating_loader', fixture=True):
    source = {'artifact_id': 'source', 'producer': None, 'data_type': 'csv'}
    if fixture:
        source['fixture_ref'] = 'fixtures/inputs/source.csv'
    return {'service_intents': [{'intent_id': 'read'}],
            'artifacts': [source, {'artifact_id': 'dataset', 'producer': 'read', 'data_type': 'json'}],
            'bindings': [{'intent_id': 'read', 'service_id': service, 'service_version': '1.0.0',
                'input_bindings': [{'port': 'csv_file', 'artifact_id': 'source'}],
                'output_bindings': [{'port': 'validated_dataset', 'artifact_id': 'dataset'}],
                'parameter_bindings': {'output_path': '/workspace/data.json'}}],
            'control_flow': {'edges': [], 'branches': [], 'gates': [], 'parallel_groups': []}}


def inspect(tmp_path, doc):
    root = tmp_path / 'fixtures/inputs'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'source.csv').write_text('name,value\na,7\n')
    return analysis.analyze_ir(doc, tmp_path, Catalog(), planner.controls.load,
                               [{'name': 'nominal', 'fixture_root': 'fixtures/inputs'}])


def test_roster_support_is_never_certified_execution_readiness(tmp_path):
    data = document()
    before = copy.deepcopy(data)
    result = inspect(tmp_path, data)
    assert result['state'] == 'analyzed' and result['service_roster_complete']
    assert result['execution_ready'] is False
    assert data == before


def test_missing_service_version_not_replaced_by_similar_service(tmp_path):
    data = document()
    data['bindings'][0]['service_version'] = '9.0.0'
    result = inspect(tmp_path, data)
    assert result['missing_services'] == ['csv_tabular_schema_validating_loader@9.0.0']


def test_standalone_retention_does_not_count_as_workflow_support(tmp_path):
    result = inspect(tmp_path, document('retention_cutoff_config_resolver'))
    service = result['services'][0]
    assert service['standalone_operation_available'] and not service['workflow_dispatch_available']


def test_missing_public_input_link_retained_not_guessed(tmp_path):
    result = inspect(tmp_path, document(fixture=False))
    assert any(i['code'] == 'missing_explicit_fixture' for i in result['issues'])
    assert result['inputs'][0]['state'] == 'missing_explicit_fixture'


def test_unsupported_reference_form_is_not_called_semantic_failure(tmp_path):
    data = document()
    data['artifacts'][0]['fixture_ref'] = '/data/source.csv'
    result = inspect(tmp_path, data)
    assert result['inputs'][0]['state'] == 'fixture_reference_form_unsupported'
    assert 'semantic' not in json.dumps(result)


def test_free_text_gate_and_branch_require_explicit_translation(tmp_path):
    data = document()
    data['control_flow']['gates'] = [{'condition': 'available == true'}]
    data['control_flow']['branches'] = [{'cases': []}]
    result = inspect(tmp_path, data)
    codes = {i['code'] for i in result['issues']}
    assert 'original_gate_translation_required' in codes
    assert 'original_branch_and_merge_translation_required' in codes


def test_cycle_and_unbound_ports_reported(tmp_path):
    data = document()
    data['control_flow']['edges'] = [{'from': 'read', 'to': 'read'}]
    data['bindings'][0]['input_bindings'] = []
    result = inspect(tmp_path, data)
    codes = {i['code'] for i in result['issues']}
    assert 'dependency_cycle_or_unresolved_parent' in codes
    assert 'required_service_port_unbound' in codes


def test_schema_reference_inspected_but_not_fetched(tmp_path):
    path = tmp_path / 'schema.json'
    path.write_text(json.dumps({'type': 'object', 'properties': {'x': {'$ref': 'https://example.invalid/schema'}}}))
    result = analysis.schema_review('schema.json', tmp_path, planner.controls.load)
    assert result['state'] == 'reference_resolution_review' and result['reference_count'] == 1
    assert analysis.schema_review('../private.json', tmp_path, planner.controls.load)['state'] == 'schema_inspection_error'


def test_network_credentials_and_cleanup_flagged(tmp_path):
    class RiskCatalog(Catalog):
        def get(self, *args):
            data, _ = super().get(*args)
            data['policies'] = {'network_access': 'required', 'secret_access': 'required'}
            data['capability']['operations'] = ['Delete old data']
            return data, None
    data = document('external_cleanup')
    result = analysis.analyze_ir(data, tmp_path, RiskCatalog(), planner.controls.load, [])
    assert result['network_required_services'] and result['credential_review_services'] and result['destructive_review_services']


def reference(case, services, **counts):
    return {'case': case, 'analysis': {'state': 'analyzed', 'missing_services': services,
        'issue_counts': counts, 'network_required_services': [], 'credential_review_services': [], 'destructive_review_services': []}}


def test_ranking_ignores_semantic_scores_model_success_and_availability():
    refs = [reference('main/a', ['x']), reference('main/b', ['x', 'y']), reference('main/c', ['z'])]
    first = analysis.propose_cohorts(refs, 3)
    altered = copy.deepcopy(refs)
    for index, ref in enumerate(altered):
        ref['semantic_success'] = 1 - index
        ref['model_cells_available'] = index * 100
        ref['analysis']['node_f1'] = index
    assert analysis.propose_cohorts(altered, 3) == first
    assert first['tentative_shared_implementation_cohort'] == ['main/a', 'main/b']


def test_no_local_shortlist_when_only_deletion_candidate():
    item = reference('main/cleanup', ['cleanup'])
    item['analysis']['destructive_review_services'] = ['cleanup']
    result = analysis.propose_cohorts([item], 3)
    assert result['conservative_local_shortlist'] == []
    assert result['status'] == 'proposal_requires_review_not_execution_authorization'


def test_direct_argo_inventoried_not_run_or_translated(tmp_path):
    path = tmp_path / 'workflow.yaml'
    path.write_text('kind: Workflow\nspec:\n  templates:\n  - script:\n      image: python:3.12-slim\n      source: "raise RuntimeError(\'must not execute\')"\n')
    result = planner.inspect_argo(path, 10000)
    assert result['state'] == 'direct_artifact_inventoried'
    assert result['script_templates'] == 1 and result['execution_ready'] is False
    assert result['route'] == 'direct_argo'


def test_missing_oversized_and_invalid_documents_preserved(tmp_path):
    missing = tmp_path / 'missing.yaml'
    assert analysis.read_document(missing, planner.controls.load, 100)[1] == 'missing_artifact'
    path = tmp_path / 'data.yaml'
    path.write_text('x' * 101)
    assert analysis.read_document(path, planner.controls.load, 100)[1] == 'inspection_limit'
    path.write_text('bad: [')
    assert analysis.read_document(path, planner.controls.load, 100)[1].startswith('parse_or_shape_error')


def test_recursive_yaml_does_not_loop_in_static_traversal(tmp_path):
    path = tmp_path / 'data.yaml'
    path.write_text('root: &self\n  same: *self\n')
    data, error = analysis.read_document(path, planner.controls.load, 1000)
    assert error is None
    assert len(list(analysis.walk(data))) < 5


def test_summary_preserves_unavailable_and_direct_route_cells():
    record = {'reference': reference('main/a', ['x']), 'model_cells': [
        {'source': {'id': 'a', 'case': 'main/a', 'route': 'serviceflow_ir'}, 'analysis': {'state': 'missing_artifact'}},
        {'source': {'id': 'b', 'case': 'main/a', 'route': 'direct_argo'}, 'analysis': {'state': 'direct_artifact_inventoried'}}]}
    combined = planner.summarize([record], 3)
    assert combined['original_model_cell_count'] == 2 and combined['execution_ready_cells'] == 0
    assert combined['cell_states']['missing_artifact'] == 1
    assert set(combined['proposals']['proposed_original_cell_roster']) == {'a', 'b'}


def test_catalog_never_reads_private_relationships(tmp_path):
    root = tmp_path / 'catalog/services'
    root.mkdir(parents=True)
    descriptor = root / 'service.yaml'
    descriptor.write_text('service_id: local\nversion: 1.0.0\n')
    sha = planner.controls.sha256(descriptor)
    (root.parent / 'catalog.yaml').write_text(f'services:\n- service_id: local\n  version: 1.0.0\n  descriptor_path: services/service.yaml\n  sha256: {sha}\n')
    (tmp_path / 'workspace.yaml').write_text(f'files:\n- path: catalog/services/service.yaml\n  sha256: {sha}\n')
    catalog = analysis.Catalog(planner.controls.load)
    assert catalog.get(tmp_path, 'local', '1.0.0')[1] is None
    assert catalog.get(tmp_path, 'local', '2.0.0')[1] == 'service_version_absent_from_public_catalog'


def test_source_descriptor_digest_not_confused_with_sanitized_bytes(tmp_path):
    root = tmp_path / 'catalog/services'
    root.mkdir(parents=True)
    descriptor = root / 'service.yaml'
    descriptor.write_text('service_id: local\nversion: 1.0.0\n')
    actual = planner.controls.sha256(descriptor)
    (root.parent / 'catalog.yaml').write_text('services:\n- service_id: local\n  version: 1.0.0\n  descriptor_path: services/service.yaml\n  sha256: original_source_digest\n')
    (tmp_path / 'workspace.yaml').write_text(f'files:\n- path: catalog/services/service.yaml\n  sha256: {actual}\n')
    catalog = analysis.Catalog(planner.controls.load)
    assert catalog.get(tmp_path, 'local', '1.0.0')[1] is None


def test_planner_checkpoint_outputs_and_resume_without_reinspection(tmp_path, monkeypatch):
    """Exercise report/checkpoint plumbing with one synthetic, nonexecuted cell."""
    from types import SimpleNamespace
    config = tmp_path / 'config.json'
    policy = {'package_version': 'test', 'audit_protocol_version': 'test', 'parent_family_run': 'parent',
              'expected_original_pipelines': 1, 'methods': ['m3'], 'max_document_bytes': 1000, 'cohort_size': 1}
    planner.controls.write_json(config, policy)
    parent_dir = tmp_path / 'parent'
    planner.controls.write_json(parent_dir / 'run.json', {'status': 'complete', 'source_inputs_unchanged': True,
                                                        'environment': {'test': True}})
    planner.controls.write_json(parent_dir / 'input_sha256.json', {})
    family_config = tmp_path / 'family.json'
    planner.controls.write_json(family_config, {'parent_replay': 'replay'})
    inventory_dir = tmp_path / 'inventory'
    planner.controls.write_json(tmp_path / 'replay/run.json', {'inventory_directory': str(inventory_dir)})
    batch = tmp_path / 'batch.json'
    planner.controls.write_json(batch, {})
    planner.controls.write_json(inventory_dir / 'run.json', {'control_directory': str(tmp_path / 'baseline'),
        'sources': [{'case': 'main/example', 'kind': 'reference'}], 'batches': [str(batch)]})
    artifact = tmp_path / 'final.yaml'
    artifact.write_text('{}')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    sources = [{'id': 'model/m3/main/example/0', 'case': 'main/example', 'model': 'model', 'method': 'm3',
                'route': 'serviceflow_ir', 'manifest': str(manifest), 'artifact': str(artifact)}]
    monkeypatch.setattr(planner, 'ROOT', tmp_path)
    monkeypatch.setattr(planner, 'CONFIG', config)
    monkeypatch.setattr(planner, 'FILES', [config])
    monkeypatch.setattr(planner.family, 'CONFIG', family_config)
    monkeypatch.setattr(planner.controls, 'environment', lambda: {'test': True})
    monkeypatch.setattr(planner.parent, 'verify_hashes', lambda *a: {})
    monkeypatch.setattr(planner, 'collect_cells', lambda *a: sources)
    monkeypatch.setattr(planner.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout='synthetic checks passed', stderr=''))
    monkeypatch.setattr(planner, 'case_record', lambda *a: {'reference': reference('main/example', ['x']),
        'model_cells': [{'source': sources[0], 'analysis': {'state': 'missing_artifact'}}]})
    assert planner.main([]) == 0
    output = next((tmp_path / 'audit/outputs').iterdir())
    assert planner.replay.read_json(output / 'aggregate_coverage.json')['original_model_cell_count'] == 1
    assert 'main/example' in (output / 'summary.md').read_text()
    monkeypatch.setattr(planner, 'case_record', lambda *a: pytest.fail('Completed case was inspected again'))
    assert planner.main(['--resume', str(output)]) == 0
