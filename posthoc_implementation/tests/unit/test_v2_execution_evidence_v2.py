"""Execution-evidence controls use authored inputs, never model inference."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v2_execution_evidence_replay_v2 as runner

c,k=runner.compiler,runner.compiler.kernel


def test_actual_csv_and_declared_upstream_pass_with_no_private_fixture_leak(tmp_path):
    row,result=runner.authored_case(tmp_path/'case')
    assert result['role_matched_assertion_pass'] and result['profile_conformance']['pass']
    root=tmp_path/'case/result/evaluation/scenarios/test/snapshot'
    first=json.loads((root/'artifacts/source_status.json').read_text())
    final=json.loads((root/'artifacts/final_status.json').read_text())
    assert first['fixture']['record_count']==2 and first['fixture']['file_count']==1
    assert final['upstream_artifact_count']==1 and final['upstream_artifacts'][0]['artifact_id']=='source_status'
    assert all('private_expected' not in f['name'] for f in first['fixture']['files'])
    assert [t['intent_id'] for t in row['compilation']['runtime']['tasks']]==['source','final']


@pytest.mark.parametrize('mode',['empty','broken_upstream'])
def test_false_evidence_does_not_become_a_positive_assertion_pass(tmp_path,mode):
    row,result=runner.authored_case(tmp_path/mode,mode)
    if mode=='broken_upstream':
        assert result['state']=='blocked_execution_profile' and not result['role_matched_assertion_pass']
        assert not result['profile_conformance']['pass']
        return
    assert not result['role_matched_assertion_pass'] and result['execution_errors']
    root=tmp_path/mode/'result/evaluation/scenarios/test/snapshot/artifacts'
    packets=[json.loads(p.read_text()) for p in root.glob('*.json')]
    assert packets and any(not p['execution_evidence']['success'] for p in packets)
    assert result['profile_conformance']['pass']  # truthful rejection is a valid profile outcome


def test_corrupt_fixture_is_rejected_before_execution_and_by_the_kernel(tmp_path):
    with pytest.raises(json.JSONDecodeError):runner.authored_case(tmp_path/'corrupt','corrupt')
    fixture,errors=k.fixture_observation(tmp_path/'corrupt/public/fixtures/inputs')
    assert errors and fixture['record_count']==0


def test_wrong_private_count_stays_wrong_and_cannot_change_compilation(tmp_path):
    row,result=runner.authored_case(tmp_path/'case')
    public=c.previous.PublicWorkspace(tmp_path/'case/public');source=tmp_path/'case/source';instance=tmp_path/'case/reviewed'
    first=c.extend(c.previous.compile_plan(source,public),source,public,instance,runner.read(runner.PROFILE))
    definition={'assertion_id':'count','type':'json_path_equals','path':'artifacts/source_status.json','json_path':'fixture.record_count','expected':999}
    scored=runner.evaluator.score(tmp_path/'case/result/evaluation/scenarios/test/snapshot',{'scenario':'test','_errors':[]},[definition])
    assert not scored['reviewed_assertion_pass']
    runner.write(instance/'gold/assertions.yaml',{'expected':999})
    public=c.previous.PublicWorkspace(tmp_path/'case/public')
    after=c.extend(c.previous.compile_plan(source,public),source,public,instance,runner.read(runner.PROFILE))
    assert after==first


def test_modified_upstream_file_is_rejected_using_actual_producer_receipt(tmp_path):
    row,result=runner.authored_case(tmp_path/'case')
    root=tmp_path/'case/result/evaluation/scenarios/test/snapshot'
    source_path=next(w['path'] for w in row['compilation']['writers'] if w['intent_id']=='source')
    (root/source_path).write_text('{"success":true}')
    task=next(s['task_evidence'] for s in row['compilation']['scripts'] if s['task_evidence']['intent_id']=='final')
    observation=k.execution_observation(SimpleNamespace(workspace=root,fixtures=tmp_path/'case/public/fixtures/inputs'),task)
    assert not observation['success'] and observation['upstream_artifact_count']==0


def test_absent_actual_producer_receipt_is_rejected(tmp_path):
    row,_=runner.authored_case(tmp_path/'case')
    root=tmp_path/'case/result/evaluation/scenarios/test/snapshot'
    (root/'execution_receipts/source.json').unlink()
    task=next(s['task_evidence'] for s in row['compilation']['scripts'] if s['task_evidence']['intent_id']=='final')
    observed=k.execution_observation(SimpleNamespace(workspace=root,fixtures=tmp_path/'case/public/fixtures/inputs'),task)
    assert not observed['success'] and observed['upstream_artifact_count']==0


def test_forged_counters_fail_profile_conformance(tmp_path):
    row,result=runner.authored_case(tmp_path/'case')
    relative=next(w['path'] for w in row['compilation']['writers'] if w['intent_id']=='final')
    path=tmp_path/'case/result/evaluation/scenarios/test/snapshot'/relative
    value=json.loads(path.read_text());value['execution_evidence']['fixture']['record_count']=999;path.write_text(json.dumps(value))
    checked=c.conformance(tmp_path/'case/result/evaluation',row['compilation'],result,runner.read(runner.PROFILE))
    assert not checked['pass']


def test_forged_per_file_count_and_matching_total_are_recomputed(tmp_path):
    row,result=runner.authored_case(tmp_path/'case')
    relative=next(w['path'] for w in row['compilation']['writers'] if w['intent_id']=='final')
    path=tmp_path/'case/result/evaluation/scenarios/test/snapshot'/relative
    value=json.loads(path.read_text());evidence=value['execution_evidence']
    evidence['fixture']['record_count']=999;evidence['fixture']['files'][0]['record_count']=999
    path.write_text(json.dumps(value))
    checked=c.conformance(tmp_path/'case/result/evaluation',row['compilation'],result,runner.read(runner.PROFILE))
    assert not checked['pass']


def test_topology_does_not_invent_edges_and_cycles_are_rejected():
    tasks=[{'intent_id':'b','dependencies':['a']},{'intent_id':'a','dependencies':[]}]
    ordered=c.stable_topology(tasks)
    assert ordered==[tasks[1],tasks[0]] and tasks[0]['dependencies']==['a']
    with pytest.raises(ValueError):c.stable_topology([{'intent_id':'a','dependencies':['b']},{'intent_id':'b','dependencies':['a']}])


@pytest.mark.parametrize('kind',['status','notification','any'])
def test_registered_types_accept_a_real_observation_without_private_values(kind):
    class Public:
        def descriptor(self,*args):return {'interface':{'outputs':[{'name':'result','data_type':kind}]},'invocation':{'mock_supported':True}},'catalog/service.yaml'
    spec={'after':{'artifact_id':'out','data_type':kind},'state':'unchanged_no_concrete_schema'}
    ok,schemas,reason=c.eligible(spec,{}, {'service_id':'s','service_version':'1'},'result',Public(),runner.read(runner.PROFILE))
    assert ok and schemas==[] and reason=='registered_execution_evidence'


def test_closed_public_schema_is_preserved_and_not_silently_relaxed():
    class Public:
        def descriptor(self,*args):return {'interface':{'outputs':[{'name':'result','data_type':'status'}]},'contracts':[]},'catalog/service.yaml'
        def read(self,path):return {'type':'object','additionalProperties':False,'required':['success'],'properties':{'success':{'type':'boolean'}}}
    record={'after':{'artifact_id':'a','data_type':'status','json_value':{'success':True}},'state':'unchanged_valid_public_example'}
    before=copy.deepcopy(record)
    ok,_,reason=c.eligible(record,{'schema_ref':'contracts/status.json'},{'service_id':'s','service_version':'1'},'result',Public(),runner.read(runner.PROFILE))
    assert not ok and reason=='public_schema_disallows_profile' and record==before


def test_scalar_or_array_public_output_cannot_be_replaced_with_telemetry_object():
    class Public:
        def descriptor(self,*args):return {'interface':{'outputs':[{'name':'result','data_type':'any'}]}},'catalog/service.yaml'
    record={'after':{'artifact_id':'a','data_type':'any','json_value':[]},'state':'unchanged_valid_public_example'}
    ok,_,reason=c.eligible(record,{}, {'service_id':'s','service_version':'1'},'result',Public(),runner.read(runner.PROFILE))
    assert not ok and reason=='non_object_public_value'


def test_json_control_manifest_is_not_a_data_record_and_is_not_copied(tmp_path):
    (tmp_path/'fixture.json').write_text(json.dumps({'pipeline_id':'authored','inputs':{'data':'data.csv'},'input_modalities':['table']}))
    (tmp_path/'data.csv').write_text('x\n1\n2\n3\n')
    observed,errors=k.fixture_observation(tmp_path)
    assert not errors and observed['file_count']==1 and observed['record_count']==3
    assert 'manifest' not in observed and observed['configuration_files'][0]['name']=='fixture.json'


def test_existing_domain_values_are_not_repaired_to_match_targets():
    spec={'artifact_id':'a','json_value':{'success':False,'row_count':99}}
    packet=k.evidence_payload(spec,c.example_observation())
    assert packet['success'] is False and packet['row_count']==99 and packet['execution_evidence']['success'] is True


def test_repeated_identical_write_is_one_physical_upstream_artifact(tmp_path):
    row,result=runner.authored_case(tmp_path/'case')
    source=tmp_path/'case/source';spec={'artifact_id':'source_status','data_type':'status','media_type':'application/json'}
    (source/'runtime/scripts/source.py').write_text(c.previous.original._script_text([spec,spec]))
    public=c.previous.PublicWorkspace(tmp_path/'case/public')
    row['compilation']=c.extend(c.previous.compile_plan(source,public),source,public,tmp_path/'case/reviewed',runner.read(runner.PROFILE))
    result=runner.execute(row,tmp_path/'case/repeated_result',runner.read(runner.PROFILE))
    assert result['role_matched_assertion_pass'] and result['profile_conformance']['pass']
    receipt=json.loads((tmp_path/'case/repeated_result/evaluation/scenarios/test/snapshot/execution_receipts/source.json').read_text())
    assert len(receipt['outputs'])==1


def test_multi_producer_binding_keeps_distinct_real_output_versions(tmp_path):
    row,_=runner.authored_case(tmp_path/'case');source=tmp_path/'case/source'
    ir=c.previous.metadata.document(source/'serviceflow.yaml')
    ir['artifacts'][0]['producer']=['source','source2']
    other=copy.deepcopy(ir['bindings'][0]);other['intent_id']='source2';ir['bindings'].append(other)
    runner.write(source/'serviceflow.yaml',ir)
    runtime=c.previous.metadata.document(source/'runtime/manifest.yaml')
    runtime['tasks'].append({'intent_id':'source2','script':'scripts/source2.py','dependencies':[],
        'arguments':['--workspace','{workspace}','--fixtures','{fixtures}']})
    runner.write(source/'runtime/manifest.yaml',runtime)
    (source/'runtime/scripts/source2.py').write_text(c.previous.original._script_text([{'artifact_id':'source_status','data_type':'status','media_type':'application/json'}]))
    public=c.previous.PublicWorkspace(tmp_path/'case/public')
    row['compilation']=c.extend(c.previous.compile_plan(source,public),source,public,tmp_path/'case/reviewed',runner.read(runner.PROFILE))
    result=runner.execute(row,tmp_path/'case/multiple_result',runner.read(runner.PROFILE))
    assert result['role_matched_assertion_pass'] and result['profile_conformance']['pass']
    root=tmp_path/'case/multiple_result/evaluation/scenarios/test/snapshot'
    packet=json.loads((root/'artifacts/final_status.json').read_text())
    assert packet['upstream_artifact_count']==2
    assert len({u['path'] for u in packet['upstream_artifacts']})==2
    assert [t['intent_id'] for t in row['compilation']['runtime']['tasks']]==['source','source2','final']
