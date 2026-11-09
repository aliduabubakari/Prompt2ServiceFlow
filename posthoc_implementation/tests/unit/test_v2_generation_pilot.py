"""Lossless transport, visibility, error logging and at-most-once inference tests.

All API responses here are scripted local fakes. No paid model calls or saved
model-code execution occurs during preparation or the pilot verification gate.
"""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v2_generation_pilot as pilot


def schema():return pilot.replay.read_json(ROOT/'schemas/serviceflow_ir.schema.json')


def metadata():
    return {'ir_version':'0.1.0','composition_id':'unit_composition',
        'catalog_snapshot':{'catalog_id':'serviceflow_catalog','version':'1.0.0','sha256':'a'*64},
        'source':{'dataset_id':'zenodo_pipeline_descriptions','dataset_version':'v1.0.0','benchmark_id':'main:unit',
                  'split':'main','pipeline_id':'unit','description_path':'task.md','description_sha256':'b'*64}}


def document():
    return {**metadata(),'requirement':{'name':'Unit','purpose':'Read and validate synthetic input.','domain':'ETL',
        'execution_model':'batch','topology':'linear','information_sufficiency':'high','notes':[]},
        'schedule':{'type':'manual','catchup':False},'external_systems':[],
        'service_intents':[{'intent_id':'read','name':'Read','category':'Extractor','capability':'Read synthetic local input.',
            'source_step_refs':['read_source'],'evidence':[{'source':'description','text':'Read input records.','line_start':1}],
            'inputs':['source'],'outputs':['output'],'external_system_refs':[],'preconditions':[],
            'effects':['Produces the declared output.'],'required_policy_properties':{'network_access':'forbidden','secret_access':'forbidden','idempotency':'preferred'},
            'decomposition_rationale':'The task explicitly requests reading.','confidence':'explicit','ambiguity':{'status':'none','notes':[]}}],
        'source_step_accounting':[{'source_step_ref':'read_source','disposition':'service','intent_ids':['read'],'rationale':'Read source is the declared source step.'}],
        'control_flow':{'edges':[],'parallel_groups':[],'branches':[],'gates':[]},
        'artifacts':[{'artifact_id':'source','name':'Input','kind':'artifact','data_type':'csv','role':'input','producer':None,'consumers':['read'],
            'sensitivity':'internal','persistence':'workflow','fixture_ref':'fixtures/inputs/data.csv'},
            {'artifact_id':'output','name':'Output','kind':'artifact','data_type':'json','role':'output','producer':'read','consumers':[],
             'sensitivity':'internal','persistence':'workflow'}],
        'bindings':[{'intent_id':'read','service_id':'unit_loader','service_version':'1.0.0',
            'input_bindings':[{'port':'data','artifact_id':'source'}],'output_bindings':[{'port':'out','artifact_id':'output'}],
            'parameter_bindings':{'nested_payload':{'intent_id':'do_not_encode_this','pairs':[['keep','unchanged']], 'nullable':None}},
            'secret_bindings':[],'rationale':'The public contract requests this loader.','confidence':'explicit'}],
        'policies':{'default_retries':0,'default_retry_delay_seconds':0,'fail_fast':True,'service_overrides':[],
            'governance':{'allowed_sensitivities':['internal'],'network_default':'forbidden','secret_placeholders_only':True}},
        'runtime':{'target':'argo-workflows','version':'3.5.0','namespace':'audit','service_account':'audit',
            'artifact_repository':{'type':'none','reference':None},'execution_profile':'mock'},
        'validation_expectations':[{'gate':'G'+str(i),'expected_status':'pass','checks':['Authored expectation, not an observed result.']} for i in range(7)]}


def config():return {'model_name':'unit-model','base_url':'http://localhost:1234/v1','api_key_env':'UNIT_TOKEN','max_tokens':16384,'temperature':0.2,'top_p':1.0,'seed':101,'request_timeout_s':30}


def payload(content,finish='stop',**message_fields):
    return {'status':'response_received','latency_s':1,'response':{'id':'response-id','model':'reported-unit',
        'choices':[{'finish_reason':finish,'message':{'role':'assistant','content':content,**message_fields}}],
        'usage':{'completion_tokens':42,'prompt_tokens':100,'total_tokens':142}}}


class FakeClient:
    def __init__(self,raw,calls,kwargs):self.raw=raw;self.calls=calls;self.kwargs=kwargs;self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def create(self,**request):
        self.calls.append({'client':self.kwargs,'request':request})
        if isinstance(self.raw,Exception):raise self.raw
        return self.raw


def factory(raw,calls):return lambda **kwargs:FakeClient(raw,calls,kwargs)


def test_codec_roundtrip_is_lossless_for_every_semantic_decision():
    source=document();before=copy.deepcopy(source);codec=pilot.compact_ir.Codec(schema(),metadata())
    compact=codec.encode(source);restored=codec.decode(compact)
    assert restored==source==before
    assert restored['bindings'][0]['parameter_bindings']==source['bindings'][0]['parameter_bindings']
    assert len(json.dumps(compact,separators=(',',':')))<len(json.dumps(source,separators=(',',':')))


def test_only_four_verified_fields_can_be_supplied_by_expansion():
    codec=pilot.compact_ir.Codec(schema(),metadata());source=document()
    source['catalog_snapshot']['sha256']='c'*64
    with pytest.raises(ValueError):codec.encode(source)
    with pytest.raises(ValueError):pilot.compact_ir.Codec(schema(),{**metadata(),'bindings':[]})
    compact=codec.encode(document());compact['unexpected']='do not accept'
    with pytest.raises(Exception):codec.decode(compact)


def test_no_missing_slot_or_required_semantic_value_is_inferred():
    codec=pilot.compact_ir.Codec(schema(),metadata());compact=codec.encode(document())
    compact['record'].pop(0)
    with pytest.raises(Exception):codec.decode(compact)
    source=document();del source['bindings'][0]['parameter_bindings']
    with pytest.raises(Exception):codec.encode(source)


def test_optional_fields_union_values_and_conditional_schedule_preserved():
    codec=pilot.compact_ir.Codec(schema(),metadata());source=document()
    source['schedule']={'type':'cron','expression':'0 0 * * *','timezone':'UTC','catchup':False}
    source['artifacts'][1]['producer']=['one','two']
    source['bindings'][0]['secret_bindings']=[{'secret':'api','kubernetes_secret':'placeholder','key':'token'}]
    assert codec.decode(codec.encode(source))==source
    source['schedule'].pop('expression')
    with pytest.raises(Exception):codec.encode(source)


def test_duplicate_keys_nonfinite_numbers_and_fences_are_not_silently_repaired():
    for text in ('{"a":1,"a":2}','{"a":NaN}','```json\n{}\n```'):
        with pytest.raises(ValueError):pilot.compact_ir.strict_json(text)


def test_tool_and_reasoning_fields_are_retained_but_never_submitted_or_executed():
    raw=payload(None,'length',reasoning_content='private reasoning text',reasoning={'tokens':[1,2]},tool_calls=[])
    result=pilot.transport.observe(raw)
    assert result['status']=='output_limit' and result['text']=='' and result['empty_visible_content']
    assert set(result['reasoning_fields_present'])=={'reasoning_content','reasoning'}
    raw=payload('{}','tool_calls',tool_calls=[{'function':{'name':'do_not_execute','arguments':'{}'}}])
    assert pilot.transport.observe(raw)['status']=='unexpected_tool_call'


def test_content_shape_finish_reason_and_unknown_usage_are_explicit():
    assert pilot.transport.observe(payload(None))['status']=='empty_response'
    assert pilot.transport.observe(payload(None,'content_filter'))['status']=='content_filtered'
    assert pilot.transport.observe(payload('{}','other'))['status']=='unrecognized_finish_reason'
    assert pilot.transport.observe(payload([{'type':'text','text':'{}'}]))['text']=='{}'
    assert pilot.transport.observe(payload([{'type':'image','url':'ignored'}]))['status']=='unsupported_content_shape'
    p=payload('{}');p['response']['usage']=None
    assert pilot.transport.observe(p)['usage'] is None


def test_one_request_no_sdk_retries_and_secret_redaction():
    secret='UNIT-SECRET-DO-NOT-LOG';calls=[]
    raw=payload('{}',reasoning_content='retained')['response'];raw['api_key']=secret;raw['provider_note']='token='+secret
    args=pilot.transport.request(config(),[{'role':'user','content':'public task'}])
    result=pilot.transport.complete(config(),args,secret,factory(raw,calls))
    assert len(calls)==1 and calls[0]['client']['max_retries']==0
    assert secret not in json.dumps(result)
    assert result['response']['choices'][0]['message']['reasoning_content']=='retained'


def test_transport_exception_is_redacted_and_not_retried():
    calls=[];secret='UNIT-SECRET-DO-NOT-LOG'
    result=pilot.transport.complete(config(),{},secret,factory(RuntimeError('bad key '+secret),calls))
    assert result['status']=='inference_error' and len(calls)==1 and secret not in json.dumps(result)


def test_completion_identity_is_not_claimed_for_missing_or_multiple_choices():
    p=payload('{}');p['response']['choices']=[]
    assert pilot.transport.observe(p)['status']=='invalid_completion_shape'
    p=payload('{}');p['response']['choices']*=2
    assert pilot.transport.observe(p)['status']=='invalid_completion_shape'


def test_endpoint_cannot_include_credentials_or_query_token():
    for url in ('https://name:pass@example.invalid/v1','https://example.invalid/v1?key=secret','file:///tmp/model'):
        with pytest.raises(ValueError):pilot.transport.validate_model({**config(),'base_url':url})


def fake_diagnostic(*args,**kwargs):return {'state':'inspected','findings':[],'semantic_outcome':'not_measured'}


def test_full_and_compact_classification_produce_same_ir_without_semantic_credit(monkeypatch,tmp_path):
    monkeypatch.setattr(pilot.census.analysis,'analyze',fake_diagnostic)
    codec=pilot.compact_ir.Codec(schema(),metadata());source=document()
    for condition,value in [('full_ir_json',source),('compact_ir_json',codec.encode(source))]:
        result,expanded=pilot.classify(payload(json.dumps(value)),condition,codec,schema(),tmp_path,{'scenarios':[]})
        assert result['status']=='complete_ir' and expanded==source and result['schema_conformant']
        assert result['semantic_outcome']=='not_measured'


def test_full_metadata_mismatch_is_not_silently_fixed(tmp_path):
    codec=pilot.compact_ir.Codec(schema(),metadata());source=document();source['catalog_snapshot']['sha256']='d'*64
    result,expanded=pilot.classify(payload(json.dumps(source)),'full_ir_json',codec,schema(),tmp_path,{'scenarios':[]})
    assert result['status']=='metadata_mismatch' and expanded['catalog_snapshot']['sha256']=='d'*64


def test_complete_candidate_with_length_stop_remains_distinct(monkeypatch,tmp_path):
    monkeypatch.setattr(pilot.census.analysis,'analyze',fake_diagnostic)
    codec=pilot.compact_ir.Codec(schema(),metadata())
    result,_=pilot.classify(payload(json.dumps(document()),'length'),'full_ir_json',codec,schema(),tmp_path,{'scenarios':[]})
    assert result['status']=='complete_ir_with_length_stop' and result['schema_conformant']


def test_interrupted_dispatched_request_is_not_automatically_repeated(tmp_path):
    pilot.controls.write_json(tmp_path/'dispatched.json',{'already_dispatched':True})
    def forbidden(**kwargs):raise AssertionError('Must not create a client')
    result=pilot.run_cell(tmp_path,'full_ir_json',{},config(),'fake',None,None,tmp_path,{},forbidden)
    assert result['status']=='interrupted_outcome_unknown' and not result['automatic_redispatch']


def test_resume_existing_response_does_not_repeat_inference(monkeypatch,tmp_path):
    monkeypatch.setattr(pilot.census.analysis,'analyze',fake_diagnostic)
    codec=pilot.compact_ir.Codec(schema(),metadata());calls=[]
    raw=payload(json.dumps(document()))['response'];args=pilot.transport.request(config(),[{'role':'user','content':'public'}])
    for _ in range(2):
        result=pilot.run_cell(tmp_path,'full_ir_json',args,config(),'UNIT-SECRET',codec,schema(),tmp_path,{'scenarios':[]},factory(raw,calls))
        assert result['status']=='complete_ir' and result['codec_roundtrip_equal']
    assert len(calls)==1
    assert (tmp_path/'dispatched.json').is_file() and (tmp_path/'completion.json').is_file()
    assert 'UNIT-SECRET' not in ''.join(p.read_text() for p in tmp_path.iterdir() if p.is_file())


def test_public_metadata_reads_verified_identity_only(tmp_path):
    (tmp_path/'catalog').mkdir();(tmp_path/'task.md').write_text('public task');(tmp_path/'catalog/catalog.yaml').write_text('public catalog')
    manifest={'task':{'description_sha256':pilot.controls.sha256(tmp_path/'task.md')},
        'catalog':{'version':'1.0.0','sanitized_catalog_yaml_sha256':pilot.controls.sha256(tmp_path/'catalog/catalog.yaml')},
        'instance':{'id':'unit','split':'main','benchmark_id':'main:unit'}}
    result=pilot.public_metadata(tmp_path,manifest,{'source_dataset_id':'public','source_dataset_version':'v1'})
    assert set(result)==set(pilot.compact_ir.BOOKKEEPING)
    (tmp_path/'task.md').write_text('changed')
    with pytest.raises(ValueError):pilot.public_metadata(tmp_path,manifest,{'source_dataset_id':'public','source_dataset_version':'v1'})


def test_prompt_context_is_public_and_has_fixtures_in_both_conditions(monkeypatch,tmp_path):
    (tmp_path/'fixtures').mkdir();(tmp_path/'fixtures/data.csv').write_text('x\n1\n')
    view={'task':'PUBLIC_TASK','candidates':'PUBLIC_CANDIDATES','catalog':'PUBLIC_CATALOG','contracts':'PUBLIC_CONTRACTS','fixtures':'PUBLIC_FIXTURES'}
    monkeypatch.setattr(pilot.prompts,'build_visible_view',lambda *args,**kwargs:copy.deepcopy(view))
    for condition in ('full_ir_json','compact_ir_json'):
        messages=pilot.messages(tmp_path,{}, {},condition,schema(),metadata());text=json.dumps(messages)
        assert all(value in text for value in view.values()) and 'fixtures/data.csv' in text
        assert 'gold/' not in text


def test_completed_request_response_files_are_checked_on_resume(tmp_path):
    pilot.controls.write_json(tmp_path/'result.json',{'status':'complete_ir'})
    pilot.controls.write_json(tmp_path/'completion.json',{'recorded':'response'})
    checkpoint=pilot.output_checkpoint(tmp_path);run={'result_files':{'one':checkpoint}}
    pilot.verify_completed(run)
    pilot.controls.write_json(tmp_path/'completion.json',{'changed':'response'})
    with pytest.raises(ValueError):pilot.verify_completed(run)


def test_compact_optional_fields_cannot_override_verified_metadata():
    codec=pilot.compact_ir.Codec(schema(),metadata());value=codec.encode(document())
    assert isinstance(value['record'][-1],dict)
    value['record'][-1]['catalog_snapshot']={'catalog_id':'wrong'}
    with pytest.raises(Exception):codec.decode(value)


def test_missing_optional_values_are_not_materialized_from_schema_defaults():
    codec=pilot.compact_ir.Codec(schema(),metadata());source=document()
    source['requirement'].pop('notes');source.pop('source_step_accounting')
    restored=codec.decode(codec.encode(source))
    assert restored==source and 'notes' not in restored['requirement'] and 'source_step_accounting' not in restored


def test_sanitized_public_schema_roundtrip_does_not_require_private_evidence():
    public=schema()
    public['$defs']['evidence']['properties']['source']['enum']=['description','reviewer_inference']
    public['properties']['source']['properties'].pop('internal_spec_path',None)
    public['properties']['source']['properties'].pop('internal_spec_sha256',None)
    codec=pilot.compact_ir.Codec(public,metadata())
    assert codec.decode(codec.encode(document()))==document()


def test_uninventoried_prompt_files_are_rejected_before_inference(tmp_path):
    (tmp_path/'fixtures').mkdir();task=tmp_path/'task.md';task.write_text('public task')
    fixture=tmp_path/'fixtures/data.csv';fixture.write_text('x\n1\n')
    manifest={'files':[{'path':p.relative_to(tmp_path).as_posix(),'sha256':pilot.controls.sha256(p)} for p in (task,fixture)]}
    pilot.verify_prompt_inventory(tmp_path,manifest)
    (tmp_path/'fixtures/extra.txt').write_text('must not enter context')
    with pytest.raises(ValueError):pilot.verify_prompt_inventory(tmp_path,manifest)
