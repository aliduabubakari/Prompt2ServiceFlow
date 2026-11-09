"""General census diagnostics and fixed-roster aggregation; no saved execution."""
import copy
import csv
import itertools
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v2_corpus_census as census
A=census.analysis


def ir():
    return {'service_intents':[{'intent_id':'load','inputs':['source'],'outputs':['result']}],
        'bindings':[{'intent_id':'load','service_id':'arbitrary_local_loader','service_version':'2.0.0',
            'input_bindings':[{'port':'source','artifact_id':'source'}],
            'output_bindings':[{'port':'result','artifact_id':'result'}],
            'parameter_bindings':{'mode':'anything'},'secret_bindings':[]}],
        'artifacts':[{'artifact_id':'source','kind':'artifact','producer':None,'data_type':'csv','fixture_ref':'fixtures/inputs/data.csv'},
                     {'artifact_id':'result','producer':'load','data_type':'table'}],
        'control_flow':{'edges':[],'gates':[],'branches':[],'parallel_groups':[]}}


def descriptor():
    return {'interface':{'inputs':[{'name':'source','required':True,'cardinality':'one','data_type':'csv','channel':'artifact'}],
        'outputs':[{'name':'result','required':True,'cardinality':'many','data_type':'table','channel':'artifact'}],
        'parameters':[{'name':'mode','required':True,'type':'string'}],'secrets':[]},
        'capability':{'summary':'Parse local data','operations':['Read the supplied CSV']},
        'contracts':[],'policies':{'network_access':'forbidden','secret_access':'forbidden'},
        'invocation':{'image':'python:3.12','implementation_ref':'declared-only','mock_supported':True}}


def public(tmp_path):
    for name in ('nominal','second'):
        root=tmp_path/'fixtures/scenarios'/name;root.mkdir(parents=True,exist_ok=True);(root/'data.csv').write_text('x\n1\n')
    return [{'name':name,'fixture_root':'fixtures/scenarios/'+name} for name in ('nominal','second')]


def inspect(tmp_path,value=None,catalog_get=None,schema=None):
    if value is None:value=ir()
    original=copy.deepcopy(value)
    result=A.analyze(value,schema=schema or {'type':'object'},catalog_get=catalog_get or (lambda *_:(descriptor(),None)),
        workspace=tmp_path,scenarios=public(tmp_path),load=census.controls.load)
    assert value==original
    assert result['execution_ready'] is False and result['semantic_outcome']=='not_measured'
    return result


def codes(result,category=None):return {f['code'] for f in result['findings'] if category is None or f['category']==category}


def test_arbitrary_registered_service_and_version_have_no_window_adapter_requirements(tmp_path):
    result=inspect(tmp_path)
    assert result['state']=='inspected' and result['findings']==[]
    assert result['external_inputs'][0]['state']=='active_files_present_literal_differs'
    assert 'adapter' not in json.dumps(result)


def test_type_any_is_reported_as_literal_frozen_rule_not_semantic_failure(tmp_path):
    def catalog(*_):
        value=descriptor();value['interface']['outputs'][0]['data_type']='any';return value,None
    result=inspect(tmp_path,catalog_get=catalog)
    assert 'port_data_type_not_exact' in codes(result,'frozen_type_rule')
    assert not codes(result,'catalog_contract')
    assert 'any_port_payload_shape_unspecified' in codes(result,'runtime_semantics')


def test_optional_input_and_many_outputs_are_not_contract_violations(tmp_path):
    value=ir();value['bindings'][0]['input_bindings']=[];value['service_intents'][0]['inputs']=[]
    value['artifacts'].append({'artifact_id':'other','producer':'load','data_type':'table'})
    value['bindings'][0]['output_bindings'].append({'port':'result','artifact_id':'other'})
    value['service_intents'][0]['outputs'].append('other')
    def catalog(*_):
        d=descriptor();d['interface']['inputs'][0]['required']=False;return d,None
    result=inspect(tmp_path,value,catalog)
    assert not codes(result,'catalog_contract') and not codes(result,'dataflow')


def test_free_profile_label_is_a_semantics_review_cue_only(tmp_path):
    value=ir();value['bindings'][0]['parameter_bindings']={'operation_profile':'arbitrary_label'}
    def catalog(*_):
        d=descriptor();d['interface']['parameters']=[{'name':'operation_profile','required':True,'type':'string'}];return d,None
    result=inspect(tmp_path,value,catalog)
    assert codes(result,'runtime_semantics')=={'profile_parameter_without_enum'}
    assert not codes(result,'catalog_contract')


def test_all_catalog_errors_survive_missing_service_and_schema_errors(tmp_path):
    value=ir();value['bindings'][0]['output_bindings']=[]
    value['bindings'][0]['parameter_bindings']={'unknown':'do not disclose'}
    result=inspect(tmp_path,value,schema={'type':'object','required':['missing']})
    assert {'required_port_unbound','required_parameter_absent','unknown_parameter','intent_binding_artifact_set_mismatch'}<=codes(result,'catalog_contract')
    assert 'ir_schema_violation' in codes(result,'saved_structure')
    assert 'declared_producer_has_no_output_binding' in codes(result,'dataflow')
    assert 'do not disclose' not in json.dumps(result)


def test_unknown_service_and_checksum_fault_have_distinct_attribution(tmp_path):
    absent=inspect(tmp_path,catalog_get=lambda *_:(None,'service_version_absent_from_public_catalog'))
    assert 'service_version_absent_from_public_catalog' in codes(absent,'catalog_contract')
    fault=inspect(tmp_path,catalog_get=lambda *_:(None,'public_descriptor_checksum_mismatch'))
    assert 'public_descriptor_checksum_mismatch' in codes(fault,'inspection_error')
    assert not codes(fault,'catalog_contract')


def test_parameter_template_is_deferred_not_rejected_as_wrong_literal_type(tmp_path):
    value=ir();value['bindings'][0]['parameter_bindings']={'mode':'{{workflow.parameters.limit}}'}
    def catalog(*_):
        d=descriptor();d['interface']['parameters'][0]['type']='integer';return d,None
    result=inspect(tmp_path,value,catalog)
    assert 'parameter_template_needs_runtime_context' in codes(result,'execution_context')
    assert not codes(result,'catalog_contract')


@pytest.mark.parametrize('definition,actual', [
    ({'type':'integer'},True),({'type':'string','enum':['allowed']},'other'),
    ({'type':'number','minimum':5},4),({'type':'string','pattern':'^yes$'},'no')])
def test_explicit_parameter_constraints_are_checked_without_values_in_report(tmp_path,definition,actual):
    value=ir();value['bindings'][0]['parameter_bindings']['mode']=actual
    def catalog(*_):
        d=descriptor();d['interface']['parameters'][0].update(definition);return d,None
    assert 'parameter_constraint_violation' in codes(inspect(tmp_path,value,catalog),'catalog_contract')


def test_required_and_unknown_secrets_only_record_names_not_values(tmp_path):
    value=ir();value['bindings'][0]['secret_bindings']=[{'secret':'other','secret_ref':'NEVER_PRINT_THIS_TOKEN'}]
    def catalog(*_):
        d=descriptor();d['interface']['secrets']=[{'name':'api_token','required':True}];return d,None
    result=inspect(tmp_path,value,catalog)
    assert {'required_secret_unbound','unknown_secret_binding'}<=codes(result,'catalog_contract')
    assert 'NEVER_PRINT_THIS_TOKEN' not in json.dumps(result)


def test_malformed_from_alias_is_recorded_alongside_later_graph_errors(tmp_path):
    value=ir();value['control_flow']['edges']=[{'from_':'load','to':'load'},{'from':'missing','to':'load'},{'from':'load','to':'load'}]
    result=inspect(tmp_path,value)
    assert {'malformed_control_edge','unknown_control_endpoint','dependency_cycle'}<=codes(result,'dataflow')
    assert result['state']=='inspected'


def test_intent_binding_sets_and_duplicate_single_ports(tmp_path):
    value=ir();value['bindings'][0]['input_bindings'].append(copy.deepcopy(value['bindings'][0]['input_bindings'][0]))
    value['service_intents'][0]['outputs']=[]
    result=inspect(tmp_path,value)
    assert {'single_port_bound_multiple_times','intent_binding_artifact_set_mismatch'}<=codes(result,'catalog_contract')


def test_multi_producer_merge_is_context_but_conflicting_writers_are_defects(tmp_path):
    value=ir();second=copy.deepcopy(value['service_intents'][0]);second['intent_id']='load2';value['service_intents'].append(second)
    binding=copy.deepcopy(value['bindings'][0]);binding['intent_id']='load2';value['bindings'].append(binding)
    value['artifacts'][1]['producer']=['load','load2']
    good=inspect(tmp_path,value)
    assert 'multiple_bound_writers' in codes(good,'execution_context')
    assert not codes(good,'dataflow')
    value['artifacts'][1]['producer']='load'
    assert {'multiple_bound_writers','writer_producer_mismatch'}<=codes(inspect(tmp_path,value),'dataflow')


def test_external_missing_link_is_context_not_old_contract_violation(tmp_path):
    value=ir();del value['artifacts'][0]['fixture_ref'];value['artifacts'][0]['external_system_ref']='warehouse'
    result=inspect(tmp_path,value)
    assert 'external_input_link_unspecified' in codes(result,'input_context')
    assert not codes(result,'catalog_contract')
    assert result['external_inputs'][0]['external_system_declared']


def test_literal_and_active_scenario_presence_are_both_reported(tmp_path):
    scenarios=public(tmp_path)
    row=A.fixture_presence('fixtures/scenarios/nominal/data.csv',tmp_path,scenarios)
    assert row['literal_state']=='file' and row['active_scenario_state']=='all_files'
    (tmp_path/'fixtures/scenarios/second/data.csv').unlink()
    row=A.fixture_presence('fixtures/scenarios/nominal/data.csv',tmp_path,scenarios)
    assert row['literal_state']=='file' and row['active_scenario_state']=='not_all_files'
    row=A.fixture_presence('https://example.invalid/data.csv',tmp_path,scenarios)
    assert row['literal_state']=='nonlocal_or_unsafe'


def test_schema_reference_never_fetches_remote_or_evaluates_code(tmp_path):
    (tmp_path/'schema.json').write_text(json.dumps({'$ref':'https://example.invalid/never-fetch'}))
    row=A.schema_review('schema.json',tmp_path,census.controls.load,10000)
    assert row['state']=='reference_resolution_needed'
    assert A.schema_review('../private.json',tmp_path,census.controls.load,10000)['state']=='unmapped_or_invalid_public_schema'


def test_alias_cycles_nonjson_keys_and_limits_are_contained():
    recursive={};recursive['same']=recursive
    for value in (recursive,{1:'bad-key'}, {'rows':list(range(20))}):
        with pytest.raises((ValueError,TypeError)):A.validate_json_shape(value,10)
    shared={'x':1};A.validate_json_shape({'a':shared,'b':shared},100)


def test_symlinks_do_not_escape_public_root(tmp_path):
    workspace=tmp_path/'public';workspace.mkdir();(tmp_path/'outside.csv').write_text('private')
    (workspace/'link.csv').symlink_to(tmp_path/'outside.csv')
    row=A.fixture_presence('link.csv',workspace,[])
    assert row['literal_state']=='nonlocal_or_unsafe'


def test_nonlocal_operations_are_review_context_not_model_failures(tmp_path):
    def catalog(*_):
        d=descriptor();d['policies'].update(network_access='required',secret_access='required');d['capability']['operations']=['Delete old rows'];return d,None
    result=inspect(tmp_path,catalog_get=catalog)
    assert {'network_required','credentials_required','destructive_wording_review'}<=codes(result,'execution_context')
    assert not codes(result,'catalog_contract')


def cell(identity='m/model',method='m4',route='serviceflow_ir',findings=None,state='inspected'):
    return {'source':{'id':identity,'model':'model','method':method,'route':route,'case':'main/a','sample_index':0,'original_method_status':'completed'},
        'artifact_sha256':'fake','analysis':{'state':state,'findings':findings or [],'services':[],'external_inputs':[],'artifact_schemas':[]}}


def test_aggregate_counts_overlap_but_structure_dataflow_union_is_not_doubled():
    findings=[{'category':'saved_structure','code':'x'},{'category':'dataflow','code':'y'},{'category':'dataflow','code':'y'}]
    groups=census.group_counts([cell(findings=findings),cell('direct',method='m0',route='direct_argo',state='direct_artifact_inventoried')])
    group=next(g for g in groups if g['route']=='serviceflow_ir')
    assert group['cells_with_structure_or_dataflow']==1
    assert group['cells_by_category']['dataflow']==1 and group['findings_by_category']['dataflow']==2


def reference(case,services,**extra):
    return {'case':case,'analysis':{'state':'inspected','findings':[],'external_inputs':[],'artifact_schemas':[],
        'services':[{'service_id':s,'service_version':'1.0.0','signals':{}} for s in services]},**extra}


def test_family_ranking_ignores_model_results_and_prefers_reference_coverage():
    references=[reference('main/a',['s']),reference('main/b',['s']),reference('extension/c',['other'])]
    baseline=A.family_groups(references)
    modified=copy.deepcopy(references)
    for r in modified:r['model_success']=0.99;r['available_model_outputs']=500;r['analysis']['node_f1']=0
    assert A.family_groups(modified)==baseline
    assert baseline[0]['reference_pipeline_count']==2


def test_family_ranking_prioritizes_review_requirements_over_size():
    clean=reference('main/clean',['one','two'])
    risky=reference('main/risky',['single']);risky['analysis']['services'][0]['signals']['network_required']=True
    rows=A.family_groups([risky,clean])
    assert rows[0]['reference_cases']==['main/clean']


def tiny_roster():
    config={'expected_pipelines':1,'expected_strata':{'main':1},'expected_cells':2,'models':['a'],'methods':['m0','m4'],'samples':[0]}
    cases=['main/one'];sources=[]
    for m,method,case,sample in itertools.product(config['models'],config['methods'],cases,config['samples']):
        sources.append({'id':'/'.join(map(str,(m,method,case,sample))),'model':m,'method':method,'case':case,'sample_index':sample,
                        'route':'direct_argo' if method=='m0' else 'serviceflow_ir'})
    return config,cases,sources


def test_complete_crossproduct_required_not_only_matching_total():
    config,cases,sources=tiny_roster();census.verify_roster(sources,cases,config)
    sources[1]=copy.deepcopy(sources[0])
    with pytest.raises(ValueError):census.verify_roster(sources,cases,config)


def test_invalid_ir_does_not_discard_other_cell_diagnostics(tmp_path):
    scenarios=public(tmp_path);path=tmp_path/'source.yaml';path.write_text('x: [')
    config={'max_document_bytes':1000,'max_document_nodes':1000}
    assert census.inspect_ir(path,tmp_path,scenarios,{},None,config)['state']=='parse_error'
    path.write_text('null\n')
    assert census.inspect_ir(path,tmp_path,scenarios,{},None,config)['state']=='invalid_document'
    path.write_text('x'*1001)
    assert census.inspect_ir(path,tmp_path,scenarios,{},None,config)['state']=='inspection_limit'
    path.unlink()
    assert census.inspect_ir(path,tmp_path,scenarios,{},None,config)['state']=='missing_saved_ir'


def test_direct_argo_remains_static_and_separate(tmp_path,monkeypatch):
    path=tmp_path/'workflow.yaml';path.write_text('kind: Workflow\nspec:\n  templates:\n  - script:\n      image: python:3.12\n      source: "raise RuntimeError(\'must never execute\')"\n')
    def forbidden(*args,**kwargs):raise AssertionError('Saved execution forbidden')
    monkeypatch.setattr(census.controls,'_execute_scenarios',forbidden)
    source={'id':'direct','artifact':str(path),'route':'direct_argo'}
    row=census.inspect_source(source,tmp_path,{'scenarios':[]},{},None,{'max_document_bytes':10000})
    assert row['analysis']['state']=='direct_artifact_inventoried'
    assert row['analysis']['findings']==[] and row['analysis']['semantic_outcome']=='not_measured'


def test_builder_checksum_failure_is_dataset_inspection_error(tmp_path):
    workspace=tmp_path/'cases/main/a/public_workspace/main/a';workspace.mkdir(parents=True)
    (workspace/'workspace.yaml').write_text('files:\n- path: task.md\n  sha256: wrong\n')
    (workspace/'task.md').write_text('public task')
    source={'id':'one','artifact':'missing','route':'serviceflow_ir'}
    record=census.case_record('main/a',[source],tmp_path,{},None,{})
    assert record['reference']['analysis']['state']=='inspection_error'
    assert record['model_cells'][0]['analysis']['state']=='inspection_error'


def test_missing_cells_are_in_csv_without_direct_argo_contract_flags(tmp_path):
    missing=cell(state='missing_saved_ir');missing['artifact_sha256']='MISSING'
    direct=cell('direct',method='m0',route='direct_argo',state='direct_artifact_inventoried')
    cells=[missing,direct];summary={'by_model_method':census.group_counts(cells)}
    census.csv_outputs(tmp_path,summary,cells)
    with (tmp_path/'cells.csv').open(newline='') as handle:rows=list(csv.DictReader(handle))
    assert len(rows)==2 and rows[0]['state']=='missing_saved_ir' and rows[0]['artifact_present']=='False'
    assert rows[1]['catalog_contract']==''


def test_changed_checkpoint_or_cell_roster_is_rejected(tmp_path):
    source=cell()['source'];path=tmp_path/'checkpoint.json'
    record={'reference':{'case':'main/a'},'model_cells':[cell()]}
    census.controls.write_json(path,record)
    run={'sources':[source],'completed_cases':{'main/a':{'path':str(path),'sha256':census.controls.sha256(path)}}}
    assert census.read_checkpoints(run,['main/a'])==[record]
    record['model_cells'].append(cell());census.controls.write_json(path,record)
    with pytest.raises(ValueError):census.read_checkpoints(run,['main/a'])
    run['completed_cases']['main/a']['sha256']=census.controls.sha256(path)
    with pytest.raises(ValueError):census.read_checkpoints(run,['main/a'])


def test_service_variants_and_reference_ranking_remain_separate_from_model_counts():
    ref=reference('main/a',['service'])
    ref['analysis']['services'][0].update(descriptor_fingerprint='variant_a',signals={'profile_parameter_without_enum':True})
    model=cell();model['analysis']['services']=[{'service_id':'service','service_version':'1.0.0',
        'descriptor_fingerprint':'variant_b','signals':{'profile_parameter_without_enum':False}}]
    records=[{'reference':ref,'model_cells':[model]}]
    inventory=census.service_inventory(records)
    assert len(inventory)==1 and set(inventory[0]['descriptor_variants'])=={'variant_a','variant_b'}
    assert inventory[0]['model_cell_count']==inventory[0]['reference_pipeline_count']==1
