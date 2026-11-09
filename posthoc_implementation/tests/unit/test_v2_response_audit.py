"""Saved text and metadata diagnostics, with no generation or execution."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import audit_v2_saved_responses as audit
A=audit.analysis

SCHEMA={'type':'object','required':['ir_version','bindings'],'properties':{'ir_version':{'const':'0.1.0'},'bindings':{'type':'array'}},'additionalProperties':False}
IR='ir_version: 0.1.0\nbindings: []\n'
POLICY={'max_response_bytes':10000,'max_attempts_per_cell':64,'max_document_nodes':1000,'max_presentation_candidates':32}


def metadata(stage,finish=None):
    return {'stage':stage,'finish_reason':finish,'usage':{'completion_tokens':8192,'reasoning_tokens':0},'latency_s':1}


def observe(text,finish=None):
    value={'reported_finish_reason':finish,'recorded_usage':{'completion_tokens':8192,'reasoning_tokens':0},'recorded_requested_max_tokens':16384}
    return A.analyze_text(text.encode(),value,SCHEMA,POLICY)


def test_empty_text_and_length_metadata_are_separate_observations():
    row=observe('','length')
    assert row['text_state']=='empty_content' and row['reported_length_stop']
    assert row['reported_reasoning_tokens']==0
    assert row['completion_equals_recorded_requested_limit'] is False
    assert row['candidates']==[] and not row['extraction_repair_performed']


def test_whitespace_and_no_document_are_not_fabricated_ir():
    assert observe(' \n\t')['text_state']=='whitespace_only'
    assert observe('```yaml\n\n```')['text_state']=='no_documents'
    assert observe('I cannot produce this workflow.')['text_state']=='non_mapping'


def test_complete_mapping_schema_is_not_semantic_success():
    row=observe(IR)
    assert row['text_state']=='schema_conformant_ir'
    assert row['semantic_outcome']=='not_measured' and not row['extraction_repair_performed']
    assert observe('other: value')['text_state']=='mapping_schema_invalid'


def test_truncated_json_is_not_closed_or_completed():
    raw='{"ir_version":"0.1.0","bindings":[{"x":"'
    row=observe(raw,'length')
    assert row['text_state']=='parse_error_end_of_stream' and row['syntax_end_of_stream_signal']
    assert row['candidates']==[] and row['reported_length_stop']
    assert observe(raw)['reported_length_stop'] is False


def test_parseable_response_can_still_have_a_reported_length_stop():
    row=observe(IR,'length')
    assert row['text_state']=='schema_conformant_ir' and row['reported_length_stop']


def test_multiple_complete_candidates_are_not_silently_selected():
    text='```yaml\n'+IR+'```\n```yaml\n'+IR+'```\n'
    row=observe(text)
    assert len(row['candidates'])==2
    assert row['wrapper_observation']=='multiple_complete_ir_candidates'


def test_later_explicit_candidate_is_recorded_but_not_written_as_submission():
    text='```json\n{"explanation":"not an IR"}\n```\n```yaml\n'+IR+'```\n'
    row=observe(text)
    assert row['text_state']=='mapping_schema_invalid'
    assert row['wrapper_observation']=='one_complete_explicit_ir_candidate'
    assert not row['extraction_repair_performed']


def test_multiple_yaml_documents_are_visible_not_reduced_to_first():
    row=observe(IR+'---\n'+IR)
    assert row['text_state']=='multiple_documents'


def test_multifile_marker_candidate_uses_exact_complete_span():
    text='===FILE: README.md===\nnotes\n===FILE: serviceflow.yaml===\n'+IR+'===FILE: other.txt===\nother\n'
    row=observe(text)
    assert row['wrapper_observation']=='one_complete_explicit_ir_candidate'
    candidate=row['candidates'][0]
    assert text[candidate['character_start']:candidate['character_end']]==IR
    assert candidate['content_sha256']==hashlib.sha256(IR.encode()).hexdigest()


def test_candidate_offsets_are_characters_not_assumed_utf8_bytes():
    text='Résumé\n```yaml\n'+IR+'```\n'
    row=observe(text);candidate=row['candidates'][0]
    assert text[candidate['character_start']:candidate['character_end']]==IR


def test_unclosed_fences_or_incomplete_file_body_are_not_salvaged():
    assert observe('```yaml\n'+IR)['candidates']==[]
    assert observe('===FILE: serviceflow.yaml===\n{"ir_version":')['candidates']==[]


def test_inspection_limits_and_invalid_utf8_are_explicit():
    policy={**POLICY,'max_response_bytes':3}
    assert A.analyze_text(b'longer',{},SCHEMA,policy)['text_state']=='inspection_limit'
    assert A.analyze_text(b'\xff',{},SCHEMA,POLICY)['text_state']=='invalid_utf8'
    policy={**POLICY,'max_presentation_candidates':1}
    row=A.analyze_text(('```yaml\n'+IR+'```\n') .encode()*2,{},SCHEMA,policy)
    assert row['candidate_inspection_limited'] and row['wrapper_observation']=='candidate_inspection_limited'


def test_yaml_object_tags_cannot_execute(monkeypatch):
    import os
    def forbidden(*args,**kwargs):raise AssertionError('Never execute response text')
    monkeypatch.setattr(os,'system',forbidden)
    row=observe('!!python/object/apply:os.system ["touch /tmp/must-not-execute"]')
    assert row['text_state']=='parse_error_other'


def test_recorded_stage_order_wins_over_file_name_order():
    manifest={'model':{'max_tokens':16384},'usage':{'per_stage':[
        metadata('m3_ir'),metadata('m4_repair_parse'),metadata('m4_repair_parse_2'),metadata('m4_repair_parse_3','length')]}}
    before=copy.deepcopy(manifest)
    row=A.inventory(manifest,['m4_repair_parse_3','m3_ir','m4_repair_parse_2','m4_repair_parse'],'m4',64)
    assert manifest==before
    assert [a['stage'] for a in row['attempts']]==['m3_ir','m4_repair_parse','m4_repair_parse_2','m4_repair_parse_3']
    assert row['terminal_stage']=='m4_repair_parse_3' and row['attempts'][-1]['is_recorded_terminal']


@pytest.mark.parametrize('manifest,files,expected',[
    ({},['m3_ir'],'recorded_call_order_unavailable'),
    ({'usage':{'per_stage':[metadata('m3_ir'),metadata('m3_ir')]}},['m3_ir'],'repeated_stage_name_raw_history_ambiguous'),
    ({'usage':{'per_stage':[metadata('m3_ir')]}},['m3_ir','m4_repair_parse'],'saved_response_without_matching_call_metadata'),
    ({'usage':{'per_stage':[metadata('../unsafe')]}},['m3_ir'],'unknown_or_malformed_recorded_stage'),
    ({'usage':{'per_stage':[metadata('m3_ir')]}},['m3_ir','unknown'],'unrecognized_saved_response_files'),
])
def test_missing_or_ambiguous_call_metadata_never_invents_terminal(manifest,files,expected):
    row=A.inventory(manifest,files,'m4',64)
    assert expected in row['metadata_issues']
    assert row['terminal_stage'] is None and row['terminal_order_status']=='unresolved'
    assert not any(a['is_recorded_terminal'] for a in row['attempts'])


def test_missing_recorded_terminal_response_is_not_replaced_by_earlier_file(tmp_path):
    earlier=tmp_path/'earlier.txt';earlier.write_text(IR)
    terminal=tmp_path/'terminal.txt'
    value={'source':{'id':'cell'},'terminal_order_status':'resolved','terminal_stage':'m4_repair_parse',
        'attempts':[{'stage':'m3_ir','path':str(earlier),'source_sha256':audit.controls.sha256(earlier),'is_recorded_terminal':False},
                    {'stage':'m4_repair_parse','path':str(terminal),'source_sha256':'MISSING','is_recorded_terminal':True}]}
    row=audit.inspect(value,SCHEMA,POLICY)
    assert row['attempts'][0]['text_state']=='schema_conformant_ir'
    assert row['attempts'][1]['text_state']=='missing_response_file' and row['attempts'][1]['is_recorded_terminal']


def test_unknown_metadata_remains_none_not_zero():
    value=A.inventory({'usage':{'per_stage':[{'stage':'m3_ir'}]}},['m3_ir'],'m3',64)
    attempt=value['attempts'][0]
    assert attempt['reported_finish_reason'] is None and attempt['recorded_usage']['reasoning_tokens'] is None


def test_selection_keeps_parse_error_missing_ir_only_with_full_context():
    def cell(identity,status,state):return {'source':{'id':identity,'method':'m3','route':'serviceflow_ir','original_method_status':status},'analysis':{'state':state}}
    rows=[cell('a','parse_error','missing_saved_ir'),cell('b','agent_step_budget_exhausted','missing_saved_ir'),cell('c','parse_error','inspected')]
    sources,ledger=audit.select([{'model_cells':rows}],{'expected_original_cells':3,'expected_missing_ir_cells':2,'expected_selected_cells':1})
    assert [s['id'] for s in sources]==['a'] and len(ledger)==2


def test_response_symlink_cannot_escape_cell(tmp_path):
    root=tmp_path/'cell';(root/'responses').mkdir(parents=True);other=tmp_path/'outside.txt';other.write_text('private')
    (root/'responses/m3_ir.txt').symlink_to(other)
    with pytest.raises(ValueError):audit.local_response(root,'m3_ir')
    with pytest.raises(ValueError):audit.local_response(root,'../unsafe')


def test_cell_inventory_uses_whitelisted_metadata_and_reports_missing_text(tmp_path):
    manifest={'method':{'id':'m3'},'sample_index':0,'method_status':'parse_error','method_error':'no YAML documents',
              'model':{'max_tokens':16384,'api_key':'NEVER_COPY'},'usage':{'per_stage':[metadata('m3_ir','length')]}}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    value,paths=audit.cell_inventory({'id':'cell','method':'m3','sample_index':0,'manifest':str(path)},POLICY)
    assert value['attempts'][0]['source_sha256']=='MISSING' and value['terminal_stage']=='m3_ir'
    assert 'NEVER_COPY' not in json.dumps(value)


def test_counts_separate_attempts_from_terminal_cells():
    source={'model':'model','method':'m4'}
    attempts=[{'text_state':'empty_content','is_recorded_terminal':False,'reported_length_stop':True},
              {'text_state':'parse_error_end_of_stream','is_recorded_terminal':True,'reported_length_stop':True}]
    groups=A.summarize([{'source':source,'state':'audited','terminal_order_status':'resolved','attempts':attempts}])
    assert groups[0]['declared_cells']==1 and sum(groups[0]['attempt_text_states'].values())==2
    assert groups[0]['terminal_text_states']=={'parse_error_end_of_stream':1} and groups[0]['length_stop_cells']==1


def test_changed_source_or_checkpoint_is_rejected(tmp_path):
    text=tmp_path/'response.txt';text.write_text(IR)
    value={'source':{'id':'cell'},'attempts':[{'path':str(text),'source_sha256':'not-the-current-hash'}]}
    with pytest.raises(ValueError):audit.inspect(value,SCHEMA,POLICY)
    record=tmp_path/'checkpoint.json';record.write_text(json.dumps({'source':{'id':'cell'}}))
    run={'inventories':[{'source':{'id':'cell'}}],'completed_cells':{'cell':{'path':str(record),'sha256':audit.controls.sha256(record)}}}
    assert len(audit.checkpoint_records(run))==1
    record.write_text('{}')
    with pytest.raises(ValueError):audit.checkpoint_records(run)
