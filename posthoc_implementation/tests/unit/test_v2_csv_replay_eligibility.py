"""No guessed choices, repaired failures, route conversion or execution claims."""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_csv_replay_eligibility as audit

a = audit.analysis


def example(tmp_path, loader=a.SNAPSHOT):
    workspace = tmp_path / 'workspace'; nominal = workspace / 'fixtures/scenarios/nominal'; nominal.mkdir(parents=True)
    raw = b'entity,value\nA,10\nB,20\n'; (nominal / 'source.csv').write_bytes(raw)
    resource = {'driver': 'p2sf.csv-postgresql/1', 'engine': 'postgresql', 'database': 'p2sf_controls', 'schema': 'p2sf_control'}
    file_resource = {'driver': 'fixture-filesystem', 'root': '.'}
    (nominal / 'database.json').write_text(json.dumps(resource)); (nominal / 'location.json').write_text(json.dumps(file_resource))
    contract = {'loader_service': loader, 'required_columns': ['entity', 'value'], 'resource': resource, 'file_location_resource': file_resource}
    artifacts = [
        {'artifact_id': 'location', 'producer': None, 'consumers': ['detect'], 'data_type': 'object', 'fixture_ref': 'fixtures/inputs/location.json'},
        {'artifact_id': 'source', 'producer': None, 'consumers': ['validate'] + (['load'] if loader == a.SNAPSHOT else []), 'data_type': 'csv', 'fixture_ref': 'fixtures/inputs/source.csv'},
        {'artifact_id': 'database', 'producer': None, 'consumers': ['load'], 'data_type': 'object', 'fixture_ref': 'fixtures/inputs/database.json'}]
    specifications = [('detect', a.SENSOR, {'file_location_resource': 'location'}, {'availability_decision': 'decision', 'check_status': 'sensor_status'},
                       {'location_type': 'filesystem', 'path': 'source.csv', 'availability_condition': 'exists'}),
        ('validate', a.VALIDATOR, {'csv_file': 'source'}, {'validated_dataset': 'dataset', 'validated_data_object': 'metadata', 'validation_status': 'validation_status'},
         {'required_columns': ['entity', 'value'], 'has_header': True, 'delimiter': ',', 'fail_on_empty': True, 'output_path': 'artifacts/validated_dataset.json'}),
        ('load', loader, {'csv_snapshot' if loader == a.SNAPSHOT else 'ingested_data_object': 'source' if loader == a.SNAPSHOT else 'metadata', 'target_database': 'database'},
         {'target_database_reference': 'target', 'load_status': 'loaded'} if loader == a.SNAPSHOT else {'load_status': 'loaded'},
         {'import_spec': {'target_table': 'records'}, 'load_mode': 'append', 'has_header': True, 'delimiter': ','} if loader == a.SNAPSHOT else {'target_table': 'records', 'write_mode': 'append'})]
    bindings, intents = [], []
    for intent, service, ins, outs, parameters in specifications:
        bindings.append({'intent_id': intent, 'service_id': service, 'service_version': '1.0.0', 'secret_bindings': [],
            'input_bindings': [{'port': k, 'artifact_id': v} for k, v in ins.items()],
            'output_bindings': [{'port': k, 'artifact_id': v} for k, v in outs.items()], 'parameter_bindings': parameters})
        intents.append({'intent_id': intent, 'inputs': list(ins.values()), 'outputs': list(outs.values())})
        for port, identity in outs.items():
            artifacts.append({'artifact_id': identity, 'producer': intent, 'consumers': ['load'] if identity == 'metadata' and loader == a.TABULAR else [], 'data_type': a.PORTS[service][1][port]})
    ir = {'bindings': bindings, 'service_intents': intents, 'artifacts': artifacts, 'runtime': {'execution_profile': 'reference'},
          'control_flow': {'edges': [{'from': 'detect', 'to': 'validate'}, {'from': 'validate', 'to': 'load'}], 'branches': [], 'parallel_groups': [],
                           'gates': [{'sensor_intent': 'detect', 'condition': 'decision.available == true', 'gated_intents': ['validate', 'load']}]}}
    return ir, workspace, contract, hashlib.sha256(raw).hexdigest()


def analyze(parts): return a.analyze_ir(*parts)


def codes(row): return {f['code'] for f in row['findings']}


@pytest.mark.parametrize('loader', [a.SNAPSHOT, a.TABULAR])
def test_complete_static_contract_never_claims_execution_readiness(tmp_path, loader):
    parts = example(tmp_path, loader); before = copy.deepcopy(parts[0])
    row = analyze(parts)
    assert row['state'] == 'static_contract_candidate_pending_adapter', row
    assert row['execution_ready'] is False and row['semantic_outcome'] == 'not_measured'
    assert parts[0] == before


def test_unique_available_csv_does_not_fill_missing_fixture_link(tmp_path):
    parts = example(tmp_path); parts[0]['artifacts'][1].pop('fixture_ref')
    parts[0]['artifacts'][1]['external_system_ref'] = 'source'
    assert 'no_explicit_fixture_ref' in codes(analyze(parts))


def test_mock_runtime_and_resource_rebinding_are_only_hypothetical_candidates(tmp_path):
    parts = example(tmp_path); parts[0]['runtime']['execution_profile'] = 'mock'
    (parts[1] / 'fixtures/scenarios/nominal/database.json').write_text('{"driver":"filesystem-mock"}')
    before = copy.deepcopy(parts[0]); row = analyze(parts)
    assert row['state'] == 'runtime_intervention_candidate_pending_design'
    assert parts[0] == before and row['execution_ready'] is False


def test_upsert_dotted_table_and_templates_are_preserved_as_blockers(tmp_path):
    parts = example(tmp_path); p = parts[0]['bindings'][-1]['parameter_bindings']
    p['load_mode'] = 'upsert'; p['import_spec']['target_table'] = 'public.transactions'
    parts[0]['bindings'][0]['parameter_bindings']['path'] = 'transactions_{{ ds_nodash }}.csv'
    before = copy.deepcopy(parts[0]); row = analyze(parts)
    assert {'unsupported_or_missing_write_mode', 'unsupported_or_missing_target_table', 'unresolved_parameter_template'}.issubset(codes(row))
    assert parts[0] == before


def test_metadata_miswiring_and_data_type_mismatch_are_detected(tmp_path):
    parts = example(tmp_path, a.TABULAR)
    parts[0]['bindings'][-1]['input_bindings'][0]['artifact_id'] = 'dataset'
    row = analyze(parts)
    assert {'metadata_port_not_from_validator_object', 'port_artifact_type_mismatch'}.issubset(codes(row))


def test_required_columns_from_a_different_dataset_are_context_findings(tmp_path):
    parts = example(tmp_path); parts[0]['bindings'][1]['parameter_bindings']['required_columns'] = ['date', 'quantity']
    row = analyze(parts)
    assert any(f['category'] == 'public_input_context' and f['code'] == 'required_columns_absent_from_public_csv' for f in row['findings'])


def test_missing_choices_cannot_be_runtime_intervention_candidates(tmp_path):
    parts = example(tmp_path); parts[0]['bindings'][0]['parameter_bindings'].pop('path')
    parts[0]['runtime'] = {}
    row = analyze(parts)
    assert {'missing_or_invalid_sensor_path', 'runtime_profile_not_explicit'}.issubset(codes(row))
    assert row['state'] == 'blocked_saved_contract'


def test_external_metadata_cannot_bypass_the_declared_validator(tmp_path):
    parts = example(tmp_path, a.TABULAR)
    artifact = next(v for v in parts[0]['artifacts'] if v['artifact_id'] == 'metadata')
    artifact['producer'] = None; artifact['fixture_ref'] = 'fixtures/inputs/location.json'
    assert 'external_metadata_bypasses_validator_object' in codes(analyze(parts))


def test_boolean_and_required_column_types_are_not_coerced(tmp_path):
    parts = example(tmp_path); p = parts[0]['bindings'][1]['parameter_bindings']
    p['fail_on_empty'] = 'false'; p['required_columns'].append('entity')
    assert {'non_boolean_validation_flag', 'duplicate_required_columns'}.issubset(codes(analyze(parts)))


@pytest.mark.parametrize('defect', ['cycle', 'missing_edge', 'missing_gate', 'wrong_gate_artifact', 'wrong_consumers', 'duplicate_port'])
def test_graph_gate_and_port_problems_are_not_repaired(tmp_path, defect):
    parts = example(tmp_path); ir = parts[0]
    if defect == 'cycle': ir['control_flow']['edges'].append({'from': 'load', 'to': 'detect'})
    elif defect == 'missing_edge': ir['control_flow']['edges'].pop()
    elif defect == 'missing_gate': ir['control_flow']['gates'] = []
    elif defect == 'wrong_gate_artifact': ir['control_flow']['gates'][0]['condition'] = 'other.available == true'
    elif defect == 'wrong_consumers': ir['artifacts'][1]['consumers'] = []
    else: ir['bindings'][0]['input_bindings'].append(copy.deepcopy(ir['bindings'][0]['input_bindings'][0]))
    before = copy.deepcopy(ir); row = analyze(parts)
    assert row['state'] == 'blocked_saved_contract' and row['findings']
    assert ir == before


def test_malformed_structures_are_document_findings_not_inspector_crashes(tmp_path):
    parts = example(tmp_path); ir = parts[0]
    ir['runtime'] = None; ir['artifacts'][0]['consumers'] = None
    ir['service_intents'][0]['inputs'] = [{}]; ir['bindings'][0]['service_id'] = []
    ir['control_flow']['edges'] = [{'from': {}, 'to': 'load'}]
    assert analyze(parts)['state'] == 'blocked_saved_contract'


def test_schema_and_fixture_paths_never_trigger_remote_resolution(tmp_path):
    with pytest.raises(ValueError, match='Nonlocal'): audit.local_schema({'$ref': 'https://example.invalid/schema'})
    parts = example(tmp_path); parts[0]['artifacts'][1]['fixture_ref'] = '../outside.csv'
    assert 'unsafe_or_nonlocal_fixture_ref' in codes(analyze(parts))


def test_missing_yaml_cycles_and_executable_tags_are_never_executed(tmp_path):
    assert a.read_saved(tmp_path / 'absent.yaml')[1] == 'missing_saved_artifact'
    path = tmp_path / 'alias.yaml'; path.write_text('x: &x [*x]\n')
    assert a.read_saved(path)[1] == 'yaml_aliases_require_separate_review'
    path.write_text('!!python/object/apply:os.system ["touch forbidden"]')
    assert a.read_saved(path)[1] == 'parse_or_non_json_shape_error'
    assert not (tmp_path / 'forbidden').exists()


def test_direct_argo_is_inventoried_without_running_script(tmp_path):
    value = {'kind': 'Workflow', 'spec': {'templates': [{'name': 'job', 'script': {'source': 'raise RuntimeError("must not run")'}}]}}
    row = a.direct_inventory([value])
    assert row['state'] == 'direct_argo_separate_route_required' and row['script_templates'] == 1
    assert row['execution_ready'] is False


def test_complete_original_roster_keeps_failed_and_missing_cells():
    config = audit.replay.read_json(audit.CONFIG)
    sources = []
    for model, method, case, sample in itertools.product(config['models'], config['methods'], config['cases'], config['samples']):
        sources.append({'id': '/'.join(map(str, (model, method, case, sample))), 'model': model, 'method': method, 'case': case,
            'sample_index': sample, 'original_method_status': 'agent_step_budget_exhausted',
            'route': 'direct_argo' if method in ('m0', 'm1', 'm2') else 'serviceflow_ir'})
    audit.verify_roster(sources, config)
    with pytest.raises(ValueError): audit.verify_roster(sources[:-1], config)
    with pytest.raises(ValueError): audit.verify_roster(sources[:-1] + [sources[0]], config)
