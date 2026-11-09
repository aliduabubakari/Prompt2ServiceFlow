"""Independent static diagnostics; synthetic inputs, no original-cell replay."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_bounded_compatibility as runner

A = runner.analysis


def design():
    artifacts = [{'artifact_id': 'source', 'producer': None, 'data_type': 'any',
                  'fixture_ref': 'fixtures/inputs/fixture.json'}]
    intents, bindings, edges = [], [], []
    upstream = 'source'
    for i, (service, (label, _)) in enumerate(runner.previous.engine.OPERATIONS.items()):
        intent, output, report = f'stage_{i}', f'output_{i}', f'report_{i}'
        intents.append({'intent_id': intent})
        artifacts.extend([{'artifact_id': output, 'producer': intent, 'data_type': 'any'},
                          {'artifact_id': report, 'producer': intent, 'data_type': 'status'}])
        bindings.append({'intent_id': intent, 'service_id': service, 'service_version': '1.0.0',
            'input_bindings': [{'port': 'input_artifacts', 'artifact_id': upstream}],
            'output_bindings': [{'port': 'output_artifacts', 'artifact_id': output}, {'port': 'execution_report', 'artifact_id': report}],
            'parameter_bindings': {'operation_profile': label}})
        if i:
            edges.append({'from': f'stage_{i-1}', 'to': intent})
        upstream = output
    return {'service_intents': intents, 'bindings': bindings, 'artifacts': artifacts,
            'control_flow': {'edges': edges, 'branches': [], 'gates': [], 'parallel_groups': []}}


def catalog_get(service, version):
    if service not in runner.previous.engine.OPERATIONS or version != '1.0.0':
        return None, 'service_version_absent_from_public_catalog'
    return {'interface': {
        'inputs': [{'name': 'input_artifacts', 'required': False, 'cardinality': 'many'}],
        'outputs': [{'name': 'output_artifacts', 'required': True, 'cardinality': 'many'},
                    {'name': 'execution_report', 'required': True, 'cardinality': 'one'}],
        'parameters': [{'name': 'operation_profile', 'type': 'string', 'required': True},
                       {'name': 'modality_policy', 'type': 'object', 'required': False}]}}, None


def fixture(tmp_path):
    root = tmp_path / 'public'
    root.mkdir()
    (root / 'fixture.json').write_text(json.dumps({'inputs': {'readings': 'data.jsonl', 'buildings': 'registry.csv'}}))
    (root / 'data.jsonl').write_text('{}\n')
    (root / 'registry.csv').write_text('building_id\nb1\n')
    return root


def inspect(ir, root, **overrides):
    kwargs = {'schema': {'type': 'object'}, 'catalog_get': catalog_get, 'active': root,
              'operations': {s: p[0] for s, p in runner.previous.engine.OPERATIONS.items()},
              'fixture_keys': ['readings', 'buildings'], 'load_json': runner.replay.read_json}
    kwargs.update(overrides)
    before = copy.deepcopy(ir)
    result = A.analyze(ir, **kwargs)
    assert ir == before
    return result


def codes(result, category=None):
    return {f['code'] for f in result['findings'] if category is None or f['category'] == category}


def test_catalog_valid_reference_shape_never_claims_execution_or_semantics(tmp_path):
    result = inspect(design(), fixture(tmp_path))
    assert not codes(result, 'public_catalog')
    assert not codes(result, 'dataflow')
    assert not codes(result, 'adapter_limit')
    assert result['finding_counts']['public_semantics_unspecified'] == 6
    assert not result['execution_ready']
    assert result['semantic_outcome'] == 'not_measured'


def test_optional_input_is_mapping_gap_not_catalog_violation(tmp_path):
    ir = design(); ir['bindings'][0]['input_bindings'] = []
    result = inspect(ir, fixture(tmp_path))
    assert 'ingestor_has_no_explicit_input_link' in codes(result, 'v2_input_mapping')
    assert 'exact_port_arrangement_required' in codes(result, 'adapter_limit')
    assert not codes(result, 'public_catalog')


def test_multiple_data_outputs_are_catalog_allowed_but_adapter_limited(tmp_path):
    ir = design()
    ir['artifacts'].append({'artifact_id': 'extra', 'producer': 'stage_5', 'data_type': 'any'})
    ir['bindings'][-1]['output_bindings'].append({'port': 'output_artifacts', 'artifact_id': 'extra'})
    result = inspect(ir, fixture(tmp_path))
    assert not codes(result, 'public_catalog')
    assert 'exact_port_arrangement_required' in codes(result, 'adapter_limit')


def test_label_mismatch_does_not_hide_later_writer_or_fixture_errors(tmp_path):
    ir = design()
    for binding in ir['bindings']:
        binding['parameter_bindings']['operation_profile'] = 'default'
    del ir['artifacts'][0]['fixture_ref']
    ir['bindings'][1]['output_bindings'][1]['artifact_id'] = 'report_0'
    result = inspect(ir, fixture(tmp_path))
    assert result['finding_counts']['adapter_limit'] == 6
    assert {'no_explicit_fixture_link'} <= codes(result, 'v2_input_mapping')
    assert {'multiple_bound_writers', 'bound_writer_not_declared_producer', 'declared_producer_has_no_output_binding'} <= codes(result, 'dataflow')
    assert not codes(result, 'public_catalog')


def test_required_report_and_duplicate_single_port_are_catalog_violations(tmp_path):
    ir = design(); ir['bindings'][0]['output_bindings'].pop()
    ir['bindings'][1]['output_bindings'].append(copy.deepcopy(ir['bindings'][1]['output_bindings'][1]))
    result = inspect(ir, fixture(tmp_path))
    assert {'required_service_port_unbound', 'single_port_bound_multiple_times'} <= codes(result, 'public_catalog')


def test_unknown_service_does_not_hide_other_catalog_errors(tmp_path):
    ir = design(); ir['bindings'][0]['service_id'] = 'invented_service'
    ir['bindings'][1]['output_bindings'][0]['port'] = 'unknown_port'
    result = inspect(ir, fixture(tmp_path))
    assert {'service_version_absent_from_public_catalog', 'unknown_service_port', 'required_service_port_unbound'} <= codes(result, 'public_catalog')


def test_parameter_constraints_differ_from_non_enumerated_profile_values(tmp_path):
    ir = design(); ir['bindings'][0]['parameter_bindings']['operation_profile'] = True
    ir['bindings'][1]['parameter_bindings'] = {'other': 'not printed'}
    result = inspect(ir, fixture(tmp_path))
    assert {'parameter_constraint_violation', 'required_parameter_absent', 'parameter_not_in_descriptor'} <= codes(result, 'public_catalog')
    assert all('not printed' not in json.dumps(f) for f in result['findings'])


def test_enumerated_parameter_values_are_enforced(tmp_path):
    def constrained(service, version):
        descriptor, error = catalog_get(service, version)
        descriptor['interface']['parameters'][0]['enum'] = ['explicit_choice']
        return descriptor, error
    result = inspect(design(), fixture(tmp_path), catalog_get=constrained)
    assert result['finding_counts']['public_catalog'] == 6
    assert not codes(result, 'public_semantics_unspecified')


@pytest.mark.parametrize('reference,expected', [
    (None, 'no_explicit_fixture_link'),
    ('fixtures/scenarios/nominal', 'fixture_reference_form_unmapped'),
    ('fixtures/inputs/missing.json', 'fixture_target_not_file'),
    ('fixtures/inputs/.', 'fixture_reference_form_unmapped'),
    ('fixtures/scenarios/nominal/data.jsonl', 'not_v2_input_manifest'),
    ('fixtures/source_bundle', 'fixture_reference_form_unmapped'),
    ('fixtures/inputs/../../secret.json', 'fixture_reference_form_unmapped'),
])
def test_path_and_manifest_limits_are_not_old_catalog_violations(tmp_path, reference, expected):
    ir = design(); ir['artifacts'][0]['fixture_ref'] = reference
    result = inspect(ir, fixture(tmp_path))
    assert expected in codes(result, 'v2_input_mapping')
    assert not codes(result, 'public_catalog')


def test_manifest_missing_data_and_escaping_data_are_reported(tmp_path):
    root = fixture(tmp_path)
    (root / 'data.jsonl').unlink()
    assert 'v2_manifest_data_unavailable' in codes(inspect(design(), root), 'v2_input_mapping')
    (root / 'fixture.json').write_text(json.dumps({'inputs': {'readings': '../private.json', 'buildings': 'registry.csv'}}))
    assert 'manifest_not_readable_under_v2_rules' in codes(inspect(design(), root), 'v2_input_mapping')


def test_symlink_cannot_read_outside_fixture_root(tmp_path):
    root = fixture(tmp_path); secret = tmp_path / 'private.json'; secret.write_text('secret')
    (root / 'link.json').symlink_to(secret)
    ir = design(); ir['artifacts'][0]['fixture_ref'] = 'fixtures/inputs/link.json'
    def forbidden_read(path):
        raise AssertionError('No outside file may be opened')
    result = inspect(ir, root, load_json=forbidden_read)
    assert 'fixture_reference_form_unmapped' in codes(result, 'v2_input_mapping')


def test_malformed_edge_and_cycle_both_survive_schema_inspection(tmp_path):
    ir = design(); ir['control_flow']['edges'].append({'from_': 'stage_0', 'to': 'stage_1'})
    ir['control_flow']['edges'].append({'from': 'stage_5', 'to': 'stage_0'})
    result = inspect(ir, fixture(tmp_path), schema={'type': 'object', 'required': ['absent_key']})
    assert 'ir_schema_violation' in codes(result, 'saved_structure')
    assert {'malformed_control_edge', 'dependency_cycle'} <= codes(result, 'dataflow')


def test_duplicates_and_missing_artifacts_are_all_reported(tmp_path):
    ir = design(); ir['artifacts'].append(copy.deepcopy(ir['artifacts'][0]))
    ir['bindings'][0]['input_bindings'][0]['artifact_id'] = 'not_declared'
    ir['bindings'][2]['intent_id'] = 'other_intent'
    result = inspect(ir, fixture(tmp_path))
    assert {'duplicate_identifier', 'intent_binding_roster_mismatch'} <= codes(result, 'saved_structure')
    assert {'bound_artifact_undeclared', 'bound_writer_not_declared_producer'} <= codes(result, 'dataflow')


def test_untrusted_shapes_and_recursive_alias_are_contained(tmp_path):
    root = fixture(tmp_path)
    for value in [None, [], 'text']:
        assert 'document_not_object' in codes(inspect(value, root))
    value = {}; value['loop'] = value
    # Avoid deepcopy/equality helper for recursive objects.
    result = A.analyze(value, schema={}, catalog_get=catalog_get, active=root,
                       operations={}, fixture_keys=[], load_json=runner.replay.read_json)
    assert 'document_not_json_compatible' in codes(result)
    ir = design(); ir['bindings'][0]['input_bindings'] = [None, {}]
    ir['bindings'][1]['parameter_bindings'] = []
    ir['bindings'][2]['parameter_bindings']['modality_policy'] = 'wrong_type'
    result = inspect(ir, root)
    assert {'malformed_port_binding', 'parameter_bindings_not_object'} <= codes(result, 'saved_structure')
    assert 'modality_policy_outside_subset' in codes(result, 'adapter_limit')


def test_checksum_failure_is_inspection_error_not_model_contract_violation(tmp_path):
    result = inspect(design(), fixture(tmp_path), catalog_get=lambda *_: (None, 'public_descriptor_checksum_mismatch'))
    assert 'public_descriptor_checksum_mismatch' in codes(result, 'inspection_error')
    assert not codes(result, 'public_catalog')


def test_category_cell_counts_are_not_occurrence_counts():
    records = [{'analysis': {'state': 'inspected', 'findings': [
        {'category': 'adapter_limit', 'code': 'x'}, {'category': 'adapter_limit', 'code': 'x'},
        {'category': 'dataflow', 'code': 'y'}]}},
        {'analysis': {'state': 'missing_saved_ir', 'findings': []}}]
    counts = runner.summarize(records)
    assert counts['cells_by_category']['adapter_limit'] == 1
    assert counts['findings_by_category']['adapter_limit'] == 2
    assert counts['states']['missing_saved_ir'] == 1


def test_file_inspection_keeps_missing_parse_and_limit_outcomes(tmp_path):
    path = tmp_path / 'saved.yaml'
    source = {'id': 'cell', 'artifact': str(path)}
    cell = {'source': source}; parent = {'models': {'cell': {'state': 'old'}}, 'profile': {'input_keys': {}}}
    config = {'max_document_bytes': 10}
    class Catalog:
        def get(self, *args):
            raise AssertionError('Should not request catalog for unavailable inputs')
    def call():
        return runner.inspect_cell(cell, parent, tmp_path, tmp_path, {}, config, Catalog())
    assert call()['analysis']['state'] == 'missing_saved_ir'
    path.write_text('a: [')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert call()['analysis']['state'] == 'parse_error'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    path.write_text(' ' * 11)
    assert call()['analysis']['state'] == 'inspection_limit'
