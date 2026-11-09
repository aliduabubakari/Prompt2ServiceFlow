"""Tiny probe tests use scripted responses only, never a live model."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_v2_reasoning_control as probe


def model():return {'model_name':'unit','base_url':'http://localhost:1234/v1','api_key_env':'UNIT','max_tokens':16384,'temperature':0.2,'top_p':1.0,'seed':101,'request_timeout_s':30}


def design():return {'requested_max_tokens':512,'prompt':'Return exactly {"probe":"ok","value":7}'}


def payload(content,reasoning=None,finish='stop',tokens=20):
    return {'status':'response_received','response':{'system_fingerprint':'fp_ollama','model':'unit',
        'choices':[{'finish_reason':finish,'message':{'role':'assistant','content':content,'reasoning':reasoning}}],
        'usage':{'completion_tokens':tokens}}}


def test_only_documented_control_differs_between_requests():
    original=model();settings,requests=probe.build_requests(design(),original)
    assert original==model() and settings['max_tokens']==512 and settings['temperature']==0
    a,b=copy.deepcopy(requests['server_default']),copy.deepcopy(requests['reasoning_effort_none'])
    assert b.pop('reasoning_effort')=='none' and a==b


def test_reasoning_only_length_stop_never_becomes_probe_answer():
    row=probe.evaluate(payload('',reasoning='{"probe":"ok","value":7}',finish='length',tokens=512),{'probe':'ok','value':7},512)
    assert row['status']=='output_limit' and not row['probe_json_matches'] and row['reasoning_character_counts']['reasoning']>0


def test_final_content_and_unknown_reasoning_metadata_are_distinct():
    row=probe.evaluate(payload('{"probe":"ok","value":7}'),{'probe':'ok','value':7},512)
    assert row['probe_json_matches'] and row['reasoning_character_counts']=={} and row['semantic_outcome']=='not_measured'


def test_request_acceptance_does_not_prove_control_was_applied():
    row=probe.evaluate(payload('',reasoning='still thinking',finish='length'),{'probe':'ok','value':7},512)
    assert not row['probe_json_matches'] and row['empty_visible_content']


def test_output_above_requested_budget_is_visible_without_explaining_cause():
    row=probe.evaluate(payload('',reasoning='reasoning',finish='length',tokens=8192),{},512)
    assert row['recorded_completion_exceeds_requested_limit'] is True


def test_unexpected_tool_is_not_success_even_if_argument_contains_json():
    value=payload(None);value['response']['choices'][0]['message']['tool_calls']=[{'name':'do not execute'}]
    row=probe.evaluate(value,{'probe':'ok','value':7},512)
    assert row['status']=='unexpected_tool_call' and not row['probe_json_matches']


def test_dispatched_unknown_outcome_does_not_trigger_another_call(tmp_path):
    probe.controls.write_json(tmp_path/'dispatched.json',{'unknown':True})
    def forbidden(**kwargs):raise AssertionError('No new client')
    row=probe.execute(tmp_path,{},model(),'secret',{},forbidden)
    assert row['status']=='interrupted_outcome_unknown'


def test_saved_completion_can_be_reinspected_without_network(tmp_path):
    probe.controls.write_json(tmp_path/'completion.json',payload('{"probe":"ok","value":7}'))
    def forbidden(**kwargs):raise AssertionError('No new client')
    row=probe.execute(tmp_path,{},model(),'secret',{'probe':'ok','value':7},forbidden)
    assert row['probe_json_matches']


def test_control_does_not_promise_a_server_cap_or_a_semantic_score():
    row=probe.evaluate(payload('{"probe":"ok","value":7}',tokens=10),{'probe':'ok','value':7},512)
    assert row['recorded_completion_exceeds_requested_limit'] is False
    assert row['semantic_outcome']=='not_measured'
