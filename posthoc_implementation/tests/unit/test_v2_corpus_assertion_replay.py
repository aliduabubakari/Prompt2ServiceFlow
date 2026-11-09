"""Synthetic evaluator controls, not a corpus replay or model invocation."""
from __future__ import annotations

import copy
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts'),str(ROOT/'audit/v2'),str(ROOT/'audit')]
import replay_v2_corpus_assertions as runner

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
