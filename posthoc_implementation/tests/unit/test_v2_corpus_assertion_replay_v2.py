"""Synthetic evaluator controls, not a corpus replay or model invocation."""
from __future__ import annotations

import copy
import csv
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts'),str(ROOT/'audit/v2'),str(ROOT/'audit')]
import replay_v2_corpus_assertions_v2 as runner

e=runner.engine


def docs():
    runtime={'scenarios':[{'name':'positive','parameters':{'flag':True}},{'name':'negative','parameters':{'flag':False}}]}
    assertions={'scenarios':[{'scenario':name,'assertions':[{'assertion_id':'x','type':'file_exists','path':'artifacts/status.json'}]} for name in ['positive','negative']]}
    return runtime,assertions


@pytest.mark.parametrize('kind',['duplicate_runtime','missing_reviewed','empty','duplicate_assertion','unsafe_path','no_parameters'])
def test_bad_scenario_or_predicate_coverage_never_passes(kind):
    runtime,assertions=docs()
    if kind=='duplicate_runtime':runtime['scenarios'].append(copy.deepcopy(runtime['scenarios'][0]))
    elif kind=='missing_reviewed':assertions['scenarios'].pop()
    elif kind=='empty':assertions['scenarios'][0]['assertions']=[]
    elif kind=='duplicate_assertion':assertions['scenarios'][0]['assertions']*=2
    elif kind=='unsafe_path':assertions['scenarios'][0]['assertions'][0]['path']='../outside'
    else:runtime['scenarios'][0].pop('parameters')
    with pytest.raises(ValueError):e.scenario_roster(runtime,assertions)


def test_complete_coverage_rejects_missing_duplicate_and_foreign_scenarios():
    assert e.complete(['a','b'],[{'scenario':'a'},{'scenario':'b'}])
    assert not e.complete(['a','b'],[{'scenario':'a'}])
    assert not e.complete(['a','b'],[{'scenario':'a'},{'scenario':'a'}])
    assert not e.complete(['a','b'],[{'scenario':'a'},{'scenario':'c'}])
    assert not e.complete([],[])


def test_execution_error_cannot_pass_absence_predicates(tmp_path):
    checked=e.score(tmp_path,{'scenario':'negative','_errors':['task failed']},[{'assertion_id':'absent','type':'file_absent','path':'artifacts/missing.json'}])
    assert not checked['reviewed_assertion_pass'] and checked['assertions'][0]['status']=='unscored_execution_error'


def test_missing_output_is_not_created_from_assertions(tmp_path):
    checked=e.score(tmp_path,{'scenario':'positive','_errors':[]},[{'assertion_id':'value','type':'json_path_equals','path':'artifacts/value.json','json_path':'value','expected':True}])
    assert not checked['reviewed_assertion_pass'] and not (tmp_path/'artifacts/value.json').exists()


def test_no_implicit_scenario_or_artifact_alias(tmp_path):
    e.write(tmp_path/'artifacts/model_chosen_name.json',{'value':True})
    checked=e.score(tmp_path,{'scenario':'nominal','_errors':[]},[{'assertion_id':'value','type':'json_path_equals','path':'artifacts/reference_name.json','json_path':'value','expected':True}])
    assert not checked['reviewed_assertion_pass']


def test_checkpoint_validates_snapshot_bytes(tmp_path):
    e.write(tmp_path/'scenario/snapshot/a.json',{'value':1})
    source={'id':'example'};saved=runner.checkpoint(tmp_path,source,{'state':'replayed','business_semantics_verified':False})
    assert not runner.verify_checkpoint(saved,source)['business_semantics_verified']
    e.write(tmp_path/'scenario/snapshot/a.json',{'value':2})
    with pytest.raises(ValueError,match='snapshots changed'):runner.verify_checkpoint(saved,source)


def test_recognition_rejects_modified_programs():
    canonical=runner.trace.runtime_compiler._script_text([{'artifact_id':'status','data_type':'status','json_value':{'success':True}}])
    assert runner.trace.recognize(canonical) is not None
    assert runner.trace.recognize(canonical+'\nraise RuntimeError("not the frozen program")\n') is None


def test_actual_sandbox_scenario_handoff_and_negative_controls(tmp_path):
    result=runner.control_gate(tmp_path/'controls')
    assert result['pass'] and result['positive_gate'] and result['missing_detected'] and result['duplicate_detected'] and result['positive_reuse_detected']
    for scenario in ['first','second']:
        directory=tmp_path/'controls/genuine/scenarios'/scenario
        assert (directory/'snapshot_manifest.json').is_file() and (directory/'execution_provenance.json').is_file()
        assert e.metadata.document(directory/'execution_provenance.json')['parameters']['chosen']==('a.json' if scenario=='first' else 'b.json')


def role_docs():
    assertion={'assertion_id':'value','type':'json_path_equals','path':'artifacts/reviewed_name.json','json_path':'value','expected':True}
    reference={'bindings':[{'intent_id':'reviewed_intent','service_id':'example','service_version':'1.0'}],
               'service_intents':[{'intent_id':'reviewed_intent','source_step_refs':['step_a']}]}
    mappings={'mappings':[{'intent_id':'reviewed_intent','outputs':{'result':'reviewed_name'}}]}
    submitted={'bindings':[{'intent_id':'model_intent','service_id':'example','service_version':'1.0',
                            'output_bindings':[{'port':'result','artifact_id':'model_name'}]}],
               'service_intents':[{'intent_id':'model_intent','source_step_refs':['step_a']}]}
    writers=[{'intent_id':'model_intent','artifact_id':'model_name','path':'artifacts/model_name.json'}]
    return assertion,reference,mappings,submitted,writers


def test_unambiguous_role_selects_existing_writer_without_mutation():
    docs=role_docs(); before=copy.deepcopy(docs)
    association=e.roles.associated_path(*docs)
    assert association['state']=='unique_output_role' and association['path']=='artifacts/model_name.json'
    predicate=e.roles.predicate_copy(docs[0],association)
    assert {k:v for k,v in predicate.items() if k!='path'}=={k:v for k,v in docs[0].items() if k!='path'}
    assert docs==before


@pytest.mark.parametrize('fault',['service','version','duplicate_service','missing_port','duplicate_port','missing_writer','multiple_writer_paths','conflicting_roles'])
def test_unresolved_roles_cannot_be_chosen_by_output_or_predicate(fault):
    assertion,reference,mappings,submitted,writers=role_docs()
    if fault=='service': submitted['bindings'][0]['service_id']='different'
    elif fault=='version': submitted['bindings'][0]['service_version']='2.0'
    elif fault=='duplicate_service':
        duplicate=copy.deepcopy(submitted['bindings'][0]);duplicate['intent_id']='other'
        submitted['bindings'].append(duplicate)
        submitted['service_intents'].append({'intent_id':'other','source_step_refs':['step_a']})
    elif fault=='missing_port': submitted['bindings'][0]['output_bindings']=[]
    elif fault=='duplicate_port': submitted['bindings'][0]['output_bindings']*=2
    elif fault=='missing_writer': writers=[]
    elif fault=='multiple_writer_paths': writers.append({**writers[0],'path':'artifacts/another.json'})
    else:
        mappings['mappings'][0]['outputs']['other']='reviewed_name'
        submitted['bindings'][0]['output_bindings'].append({'port':'other','artifact_id':'another'})
        writers.append({**writers[0],'artifact_id':'another','path':'artifacts/another.json'})
    association=e.roles.associated_path(assertion,reference,mappings,submitted,writers)
    assert association['path'] is None and e.roles.predicate_copy(assertion,association) is None


@pytest.mark.parametrize('basis',['same_intent','source_steps'])
def test_repeated_service_requires_frozen_structural_disambiguation(basis):
    assertion,reference,mappings,submitted,writers=role_docs()
    duplicate=copy.deepcopy(submitted['bindings'][0]);duplicate['intent_id']='other'
    submitted['bindings'].append(duplicate)
    submitted['service_intents'].append({'intent_id':'other','source_step_refs':['different_step']})
    if basis=='same_intent':
        reference['bindings'][0]['intent_id']='model_intent'
        mappings['mappings'][0]['intent_id']='model_intent'
    association=e.roles.associated_path(assertion,reference,mappings,submitted,writers)
    assert association['path']=='artifacts/model_name.json'


def test_unmapped_paths_remain_literal_and_missing_role_cannot_pass_absence(tmp_path):
    assertion,reference,mappings,submitted,writers=role_docs()
    association=e.roles.associated_path(assertion,reference,{'mappings':[]},submitted,writers)
    assert association=={'state':'literal_unmapped','path':assertion['path']}
    assertion['type']='file_absent';submitted['bindings']=[]
    association=e.roles.associated_path(assertion,reference,mappings,submitted,writers)
    assert e.roles.predicate_copy(assertion,association) is None


def test_paired_checks_use_identical_actual_snapshot_without_renaming(tmp_path):
    assertion,reference,mappings,submitted,writers=role_docs()
    instance=tmp_path/'reference';source=tmp_path/'source'
    (instance/'fixtures/inputs').mkdir(parents=True);(source/'runtime/scripts').mkdir(parents=True)
    runtime={'tasks':[{'intent_id':'model_intent','script':'scripts/run.py','arguments':['--workspace','{workspace}','--fixtures','{fixtures}']}],
             'scenarios':[{'name':'reviewed','parameters':{},'fixture_root':'fixtures/inputs'}]}
    program=runner.trace.runtime_compiler._script_text([{'artifact_id':'model_name','data_type':'status','json_value':{'value':True}}])
    (source/'runtime/scripts/run.py').write_text(program)
    e.write(source/'runtime/manifest.yaml',runtime);e.write(source/'serviceflow.yaml',submitted)
    e.write(instance/'runtime/manifest.yaml',runtime);e.write(instance/'gold/serviceflow.yaml',reference)
    e.write(instance/'gold/artifact_mappings.yaml',mappings)
    e.write(instance/'gold/assertions.yaml',{'scenarios':[{'scenario':'reviewed','assertions':[assertion]}]})
    source_before=e.files(source)
    result=e.replay(source,instance,tmp_path/'replay','synthetic/role')
    assert not result['reviewed_assertion_pass'] and result['role_matched_assertion_pass']
    assert not result['business_semantics_verified'] and e.files(source)==source_before
    snapshot=tmp_path/'replay/scenarios/reviewed/snapshot'
    assert (snapshot/'artifacts/model_name.json').is_file() and not (snapshot/'artifacts/reviewed_name.json').exists()


def test_checkpoint_cannot_escape_assigned_cell(tmp_path):
    source={'id':'example'};saved=runner.checkpoint(tmp_path/'wrong',source,{'state':'replayed'})
    with pytest.raises(ValueError,match='outside assigned cell'):runner.verify_checkpoint(saved,source,tmp_path/'run')


def test_full_roster_report_retains_unreplayed_cells_and_separate_conditions(tmp_path):
    source={'id':'a','model':'example','method':'m4','case':'main/task','split':'main','sample_index':0,
            'published_executable_valid':True,'published_semantic_success':False}
    missing={**source,'id':'b','published_executable_valid':False}
    plan=[{'source':source,'admission':'eligible_frozen_mock'},{'source':missing,'admission':'missing_saved_ir'}]
    check=runner.checkpoint(tmp_path/'cells/a/attempt',source,{'state':'replayed','reviewed_assertion_pass':False,
        'role_matched_assertion_pass':True,'business_semantics_verified':False})
    run={'status':'running','completed_cells':{'a':check},'design':{'scope':'synthetic'}}
    runner.render(tmp_path,run,plan)
    aggregate=runner.read(tmp_path/'aggregate.json')
    assert aggregate['declared_cells']==2 and aggregate['pending_cells']==1
    assert aggregate['corrected_reviewed_assertion_passes']==0 and aggregate['role_matched_reviewed_assertion_passes']==1
    assert aggregate['real_business_semantics_verified_by_this_replay']==0
    with (tmp_path/'paired_run_level.csv').open() as handle:rows=list(csv.DictReader(handle))
    assert len(rows)==2 and rows[1]['replay_state']=='pending'
    assert rows[1]['role_matched_assertion_pass']=='' and rows[0]['business_semantics_verified']=='False'
