"""Paired-study mechanisms tested with synthetic public inputs, not model cells."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_paired_window as runner


def profile():
    value = runner.replay.read_json(runner.base.CONFIG)
    return {**value, 'package_version': '2.0.0-candidate.4', 'audit_protocol_version': '9.0.0',
            'profile_dispatch': 'external_v2_profile_overrides_all_original_string_labels'}


def ir():
    # Use only the old structural IR shape, never native code/private answers.
    return runner.controls.load(ROOT / 'benchmark/instances/extension/building_energy_window_aggregation/gold/serviceflow.yaml')


def schema():
    return runner.replay.read_json(ROOT / 'schemas/serviceflow_ir.schema.json')


def catalog_get(service, version):
    if service not in runner.engine.OPERATIONS or version != '1.0.0':
        return None, 'service_version_absent_from_public_catalog'
    return {'interface': {
        'inputs': [{'name': 'input_artifacts', 'required': False, 'cardinality': 'many', 'data_type': 'any'}],
        'outputs': [{'name': 'output_artifacts', 'required': True, 'cardinality': 'many', 'data_type': 'any'},
                    {'name': 'execution_report', 'required': True, 'cardinality': 'one', 'data_type': 'status'}],
        'parameters': [{'name': 'operation_profile', 'required': True, 'type': 'string'},
                       {'name': 'modality_policy', 'required': False, 'type': 'object'}]}}, None


class Catalog:
    def get(self, workspace, service, version):
        return catalog_get(service, version)


def fixtures(tmp_path):
    workspace = tmp_path / 'public'
    active = workspace / 'fixtures/scenarios/nominal'; active.mkdir(parents=True)
    (active / 'fixture.json').write_text(json.dumps({'inputs': {'readings': 'readings.jsonl', 'buildings': 'registry.csv'},
        'batch_window_start': '2026-01-01T00:00:00Z', 'batch_window_end': '2026-01-01T01:00:00Z',
        'window_size_minutes': 30, 'demand_threshold_pct': 85, 'power_factor_min': 0.85}))
    rows = [{'meter_id': 'm1', 'building_id': 'b1', 'timestamp': stamp, 'energy_kwh': energy, 'demand_kw': demand, 'power_factor': quality}
        for stamp, energy, demand, quality in [('2026-01-01T00:00:00Z',2.5,40,0.9),('2026-01-01T00:15:00Z',3.5,85,0.8),('2026-01-01T00:30:00Z',4,30,0.95)]]
    (active / 'readings.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (active / 'registry.csv').write_text('building_id,demand_limit_kw\nb1,100\n')
    contracts = workspace / 'contracts/artifacts'; contracts.mkdir(parents=True)
    (contracts / 'status.schema.json').write_text(json.dumps({'type':'object','required':['success','errors'],
        'properties':{'success':{'type':'boolean'},'errors':{'type':'array'}},'additionalProperties':True}))
    scenarios = tmp_path / 'scenarios'
    runner.base.prepare_scenarios(active, scenarios, profile())
    return workspace, active, scenarios


def snapshot(trace, root):
    return {'scenario': 'nominal', '_errors': [] if trace['workflow_status']=='completed' else ['workflow rejected'],
            '_snapshot': {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}}


def execute(ir_value, tmp_path, active):
    root = tmp_path / 'execution'
    trace = runner.engine.execute(ir_value, profile(), root, active)
    return trace, snapshot(trace, root)


def test_override_is_explicit_and_never_mutates_original_ir():
    value = ir()
    for b in value['bindings']:
        b['parameter_bindings']['operation_profile'] = 'different_undocumented_label'
    original = copy.deepcopy(value)
    plan = runner.engine.compile_plan(value)
    assert value == original
    assert all(x['original_label']=='different_undocumented_label' for x in plan['profile_overrides'])
    assert all(x['meaning']=='explicit_v2_override_not_proven_equivalence' for x in plan['profile_overrides'])


def test_distinct_publication_and_audit_projections_use_roles_not_order_or_ids(tmp_path):
    _, active, _ = fixtures(tmp_path)
    value = runner.reference_variants(ir())[1][2]
    publisher = next(b for b in value['bindings'] if b['service_id']==runner.oracle.base.PUBLISHER)
    publisher['output_bindings'].reverse()
    trace, raw = execute(value, tmp_path, active)
    assert trace['workflow_status']=='completed'
    assert runner.oracle.check(raw,value,active,profile(),'nominal')['pass']
    primary = runner.oracle.primary(value)
    payload = json.loads(raw['_snapshot']['artifacts/'+primary+'.json'])
    report_id = next(o['artifact_id'] for o in publisher['output_bindings'] if o['port']=='output_artifacts' and o['artifact_id']!=primary)
    report = json.loads(raw['_snapshot']['artifacts/'+report_id+'.json'])
    assert payload['metrics'][0]['energy_kwh_sum']==6
    assert 'metrics' not in report
    assert report == json.loads(raw['_snapshot'][payload['published_files']['audit']])
    assert report != payload


@pytest.mark.parametrize('mutation', ['unknown_service','unknown_parameter','true_streaming','ambiguous_output','audit_consumer','bad_writer','conditional_edge'])
def test_compatibility_does_not_relax_unrelated_constraints(mutation):
    value = runner.reference_variants(ir())[1][2]
    if mutation=='unknown_service': value['bindings'][0]['service_id']='invented_service'
    elif mutation=='unknown_parameter': value['bindings'][0]['parameter_bindings']['new_behavior']=True
    elif mutation=='true_streaming': value['bindings'][0]['parameter_bindings']['modality_policy']={'true_streaming':True}
    elif mutation=='ambiguous_output': value['artifacts'][-1]['role']='output'
    elif mutation=='audit_consumer': value['artifacts'][-1]['consumers']=[value['bindings'][0]['intent_id']]
    elif mutation=='bad_writer': value['artifacts'][-1]['producer']=value['bindings'][0]['intent_id']
    elif mutation=='conditional_edge': value['control_flow']['edges'][0]['condition']='True'
    with pytest.raises((runner.base.ops.Unsupported,ValueError)):
        runner.engine.compile_plan(value)


def apply_edits(value, edits):
    out = copy.deepcopy(value)
    for edit in edits:
        pieces=edit['path'].strip('/').split('/'); parent=out
        for piece in pieces[:-1]: parent=parent[int(piece)] if isinstance(parent,list) else parent[piece]
        if isinstance(parent,list): parent.insert(int(pieces[-1]),copy.deepcopy(edit['value']))
        else:
            assert pieces[-1] not in parent
            parent[pieces[-1]]=copy.deepcopy(edit['value'])
    return out


def test_repairs_are_exactly_logged_idempotent_and_preserve_original(tmp_path):
    _, active, _ = fixtures(tmp_path)
    damaged=runner.reference_variants(ir())[2][2]; original=copy.deepcopy(damaged)
    repaired, edits, _=runner.repairer.repair(damaged,profile(),active,catalog_get)
    assert damaged==original
    assert len(edits)==13
    assert apply_edits(damaged,edits)==repaired
    assert not list(runner.compatibility.analysis.Draft202012Validator(schema()).iter_errors(repaired))
    assert runner.engine.compile_plan(repaired)
    repeated, repeat_edits, _=runner.repairer.repair(repaired,profile(),active,catalog_get)
    assert repeated==repaired and repeat_edits==[]


def test_status_repair_requires_public_required_status_declaration(tmp_path):
    _, active, _=fixtures(tmp_path); damaged=runner.reference_variants(ir())[2][2]
    def optional(service,version):
        descriptor,error=catalog_get(service,version)
        descriptor['interface']['outputs'][1]['required']=False
        return descriptor,error
    _, edits, _=runner.repairer.repair(damaged,profile(),active,optional)
    assert [e['rule'] for e in edits]==['unique_public_manifest']


def test_multiple_valid_manifests_leave_input_unresolved(tmp_path):
    _, active, _=fixtures(tmp_path)
    (active/'second.json').write_bytes((active/'fixture.json').read_bytes())
    damaged=runner.reference_variants(ir())[2][2]
    repaired, edits, decisions=runner.repairer.repair(damaged,profile(),active,catalog_get)
    assert 'unique_public_manifest' not in [e['rule'] for e in edits]
    assert any(d['reason']=='manifest_not_unique' for d in decisions)
    assert not repaired['artifacts'][0].get('fixture_ref')


def test_existing_wrong_reference_is_preserved_not_replaced(tmp_path):
    _, active, _=fixtures(tmp_path); value=ir()
    value['artifacts'][0]['fixture_ref']='fixtures/inputs/missing.json'
    repaired, edits, _=runner.repairer.repair(value,profile(),active,catalog_get)
    assert repaired==value and edits==[]


def test_no_input_binding_or_incompatible_type_is_not_guessed(tmp_path):
    _, active, _=fixtures(tmp_path)
    for missing_binding in (True,False):
        value=ir(); del value['artifacts'][0]['fixture_ref']
        if missing_binding: value['bindings'][0]['input_bindings']=[]
        else: value['artifacts'][0]['data_type']='csv'
        repaired, edits, _=runner.repairer.repair(value,profile(),active,catalog_get)
        assert edits==[] and repaired==value


def test_manifest_symlinks_and_escaping_data_are_not_repair_evidence(tmp_path):
    _, active, _=fixtures(tmp_path)
    (active/'fixture.json').unlink()
    outside=tmp_path/'outside.json'; outside.write_text(json.dumps({'inputs':{'readings':'readings.jsonl','buildings':'registry.csv'}}))
    (active/'fixture.json').symlink_to(outside)
    assert runner.repairer.manifests(active,profile())==[]


def test_diagnostics_prevent_repair_of_ambiguous_writers_or_unknown_services(tmp_path):
    workspace,active,_=fixtures(tmp_path)
    for wrong_service in (True,False):
        value=runner.reference_variants(ir())[2][2]
        if wrong_service: value['bindings'][0]['service_id']='invented_service'
        else: value['artifacts'][1]['producer']=value['bindings'][0]['intent_id']+'bad'
        _, record=runner.effective(value,'binding_repair',workspace,active,schema(),Catalog(),profile())
        assert record['state']=='invalid_checked_contracts' and record['edits']==[]


def test_paired_conditions_have_same_inputs_but_only_repair_changes_ir(tmp_path):
    workspace,active,_=fixtures(tmp_path)
    damaged=runner.reference_variants(ir())[2][2]
    a,ma=runner.effective(damaged,'compatibility',workspace,active,schema(),Catalog(),profile())
    b,mb=runner.effective(damaged,'binding_repair',workspace,active,schema(),Catalog(),profile())
    assert a==damaged and ma['edits']==[] and ma['state']=='invalid_checked_contracts'
    assert b!=damaged and mb['state']=='ready_for_v2_scenarios'


def test_projection_mutations_are_detected_independently(tmp_path):
    _,active,_=fixtures(tmp_path); value=runner.reference_variants(ir())[1][2]
    _,raw=execute(value,tmp_path,active)
    checks=runner.negative_controls(raw,value,profile(),active,tmp_path/'negatives')
    assert set(checks)=={'constant_summary','wrong_energy','wrong_alert','missing_publication','wrong_bound_status','wrong_bound_audit'}
    assert all(c['detected'] for c in checks.values())


def test_three_control_gates_with_synthetic_inputs_and_public_schemas(tmp_path):
    workspace,active,scenarios=fixtures(tmp_path)
    for name,condition,value in runner.reference_variants(ir()):
        record,raw,effective=runner.run_condition(value,condition,profile(),workspace,active,scenarios,schema(),Catalog(),tmp_path/name)
        assert record['state']=='evaluated_under_v2',record
        assert record['profile_all_scenarios_pass'],record['scenarios']
        record['negative_controls']=runner.negative_controls(next(x for x in raw if x['scenario']=='nominal'),effective,profile(),scenarios/'scenarios/nominal',tmp_path/name/'negatives')
        assert runner.control_pass(record,name)
        if condition=='compatibility': assert record['source_ir_sha256']==record['effective_ir_sha256']
        else: assert record['source_ir_sha256']!=record['effective_ir_sha256']


def test_source_bytes_preserved_even_with_unusual_yaml_formatting(tmp_path):
    workspace,active,scenarios=fixtures(tmp_path)
    value=ir(); path=tmp_path/'source.yaml'
    path.write_text('# original formatting retained\n'+runner.controls.yaml.safe_dump(value,sort_keys=True))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    record,_,_=runner.run_condition(value,'compatibility',profile(),workspace,active,scenarios,schema(),Catalog(),tmp_path/'attempt',path)
    assert record['source_ir_sha256']==record['effective_ir_sha256']==digest
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest


def test_control_gate_does_not_accept_incomplete_negative_set():
    record={'profile_all_scenarios_pass':True,'negative_controls':{'constant_summary':{'detected':True}}}
    assert not runner.control_pass(record,'original_reference')


def test_infrastructure_error_retains_completed_edit_log(tmp_path):
    runner.controls.write_json(tmp_path/'diagnostics.json',{'state':'ready_for_v2_scenarios',
        'edits':[{'op':'add','path':'/artifacts/0/fixture_ref','value':'fixtures/inputs/fixture.json'}]})
    record=runner.failure_record(tmp_path,OSError('sandbox unavailable'),'runner_error')
    assert record['state']=='runner_error' and len(record['edits'])==1


@pytest.mark.parametrize('field,value', [('role','input'),('data_type','status')])
def test_computation_output_requires_explicit_compatible_role_and_type(field,value):
    document=ir()
    output=document['bindings'][0]['output_bindings'][0]['artifact_id']
    artifact=next(a for a in document['artifacts'] if a['artifact_id']==output)
    artifact[field]=value
    with pytest.raises(runner.base.ops.Unsupported): runner.engine.compile_plan(document)
