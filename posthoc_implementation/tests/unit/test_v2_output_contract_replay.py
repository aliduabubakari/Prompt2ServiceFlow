"""Public-contract compiler controls; no corpus execution or LLM calls."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v2_output_contract_replay as runner

c,e=runner.compiler,runner.evaluator


def test_public_contract_control_passes_and_private_target_cannot_change_output(tmp_path):
    result=runner.authored_control(tmp_path/'control')
    assert result['pass'] and result['contradictory_expected_value_rejected']
    value=json.loads((tmp_path/'control/execution/scenarios/test/snapshot/artifacts/model_output.json').read_text())
    assert value=={'accepted':False,'count':7}


@pytest.mark.parametrize('content,definition,prefix',[
    ('example\n',{'json_path':'value','expected':1},'output_format_error'),
    ('{}',{'json_path':'value','expected':1},'missing_output_field'),
    ('{"value":false}',{'json_path':'value','expected':True},'value='),
])
def test_output_defects_are_failures_without_filling_values(tmp_path,content,definition,prefix):
    path=tmp_path/'out.json';path.write_text(content)
    result=e.score(tmp_path,{'scenario':'s','_errors':[]},[{'assertion_id':'a','type':'json_path_equals','path':'out.json',**definition}])
    assert result['assertions'][0]['status']=='fail' and result['assertions'][0]['message'].startswith(prefix)
    assert not result['reviewed_assertion_pass'] and path.read_text()==content


def test_execution_error_does_not_pass_absence_predicate(tmp_path):
    result=e.score(tmp_path,{'scenario':'s','_errors':['runtime failed']},[{'assertion_id':'a','type':'file_absent','path':'out.json'}])
    assert not result['reviewed_assertion_pass'] and result['assertions'][0]['status']=='unscored_execution_error'


def test_public_schema_conjunction_uses_all_required_fields():
    schemas=[{'type':'object','required':['a'],'properties':{'a':{'const':False}}},
             {'type':'object','required':['b'],'properties':{'b':{'type':'integer','minimum':7}}}]
    assert c.public_example(schemas)=={'a':False,'b':7}


def test_conflicting_public_constraints_are_not_relaxed():
    with pytest.raises(ValueError,match='satisfies all'):c.public_example([{'const':True},{'const':False}])


def test_remote_schema_references_never_resolved():
    with pytest.raises(ValueError,match='remote'):c.public_example([{'$ref':'https://example.invalid/private'}])


@pytest.fixture
def case(tmp_path):
    root=tmp_path/'case';assert runner.authored_control(root)['pass']
    return root


@pytest.mark.parametrize('path',['gold/assertions.yaml','fixtures/expected.json','contracts/../gold/assertions.yaml','/tmp/expected.json'])
def test_public_loader_cannot_read_private_or_noncontract_inputs(case,path):
    public=c.PublicWorkspace(case/'public')
    with pytest.raises(ValueError):public.read(path)


def test_existing_valid_example_is_not_replaced_with_more_favorable_defaults(case):
    public=c.PublicWorkspace(case/'public');ir=c.metadata.document(case/'source/serviceflow.yaml')
    spec={'artifact_id':'model_output','data_type':'object','json_value':{'accepted':False,'count':99}}
    value,record=c.corrected_spec(spec,ir['artifacts'][0],ir['bindings'][0],'result',public)
    assert value==spec and record['state']=='unchanged_valid_public_example'


def test_no_concrete_contract_preserves_the_original_output_specification():
    class Public:
        def descriptor(self,*args):return {'interface':{'outputs':[{'name':'result','media_type':'application/json'}]}},'catalog/example.yaml'
    spec={'artifact_id':'a','data_type':'object'}
    after,record=c.corrected_spec(spec,{}, {'service_id':'service','service_version':'1'},'result',Public())
    assert after==spec and record['state']=='unchanged_no_concrete_schema'


def test_unresolved_model_binding_is_not_filled_in(case):
    source=case/'source';ir=c.metadata.document(source/'serviceflow.yaml');ir['bindings'][0]['output_bindings']=[]
    runner.write(source/'serviceflow.yaml',ir)
    plan=c.compile_plan(source,c.PublicWorkspace(case/'public'))
    assert plan['changed_scripts']==0 and plan['outputs'][0]['state']=='unchanged_unresolved_model_binding'
    assert plan['scripts'][0]['text']==(source/'runtime/scripts/run.py').read_text()


def test_bound_service_version_mismatch_cannot_borrow_another_contract(case):
    public=c.PublicWorkspace(case/'public');ir=c.metadata.document(case/'source/serviceflow.yaml')
    binding=copy.deepcopy(ir['bindings'][0]);binding['service_version']='other'
    spec={'artifact_id':'model_output','data_type':'object'}
    after,record=c.corrected_spec(spec,ir['artifacts'][0],binding,'result',public)
    assert after==spec and record['state']=='unchanged_unsupported_public_contract'


def test_json_null_is_written_as_json_inside_the_sandbox(tmp_path):
    root=tmp_path/'instance';(root/'runtime/scripts').mkdir(parents=True);(root/'fixtures/inputs').mkdir(parents=True)
    (root/'runtime/scripts/run.py').write_text(c.render([{'artifact_id':'a','data_type':'object','json_value':None}]))
    manifest={'tasks':[{'intent_id':'a','script':'scripts/run.py','arguments':['--workspace','{workspace}','--fixtures','{fixtures}']}],
        'scenarios':[{'name':'s','parameters':{},'fixture_root':'fixtures/inputs'}]}
    result=e._execute_scenarios(root,manifest,sandbox_generated=True,task_timeout_seconds=10)[0]
    assert result['_errors']==[] and json.loads(result['_snapshot']['artifacts/a.json']) is None


def test_materialization_preserves_ir_parameters_and_task_graph(case):
    source=case/'source';before=c.metadata.sha(source/'serviceflow.yaml')
    plan=c.compile_plan(source,c.PublicWorkspace(case/'public'));c.materialize(plan,source,case/'copy')
    assert c.metadata.sha(case/'copy/serviceflow.yaml')==before
    assert c.metadata.document(case/'copy/runtime/manifest.yaml')==c.metadata.document(source/'runtime/manifest.yaml')


def test_private_expected_output_changes_do_not_change_compiler_plan(case):
    public=c.PublicWorkspace(case/'public');before=c.compile_plan(case/'source',public)
    runner.write(case/'public/gold/assertions.yaml',{'expected':999999})
    runner.write(case/'reviewed/gold/assertions.yaml',{'expected':999999})
    after=c.compile_plan(case/'source',c.PublicWorkspace(case/'public'))
    assert after==before


def test_model_visible_sanitized_catalog_pin_and_raw_pin_are_both_explicit(case):
    public=c.PublicWorkspace(case/'public');public.manifest['catalog']['sanitized_catalog_yaml_sha256']='sanitized'
    public.check_pin({'catalog_snapshot':{'version':'test','sha256':'sanitized'}})
    public.check_pin({'catalog_snapshot':{'version':'test','sha256':'pin'}})
    with pytest.raises(ValueError):public.check_pin({'catalog_snapshot':{'version':'test','sha256':'unrelated'}})
