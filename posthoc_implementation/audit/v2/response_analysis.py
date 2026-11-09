"""Response-text/metadata observations only; never synthesize a submission.

Wrapper candidates require explicit complete fences or serviceflow file markers.
No brace/quote completion, embedded-object search, gold guidance, or execution.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import re

from jsonschema import Draft202012Validator
import yaml

import corpus_census_analysis as census
from prompt2serviceflow.experiments.extractors import extract_yaml_documents

STAGE_RE=re.compile(r'(?:m3_ir|m4_repair_parse(?:_[1-9][0-9]*)?|m4_repair_[1-9][0-9]*)\Z')
FENCE_RE=re.compile(r'^```(?:yaml|yml|json)?[ \t]*\r?\n(.*?)^```[ \t]*(?:\r?\n|$)',re.MULTILINE|re.DOTALL|re.IGNORECASE)
MARKER_RE=re.compile(r'^===FILE:[ \t]*(\S+?)[ \t]*(?:===)?[ \t]*\r?\n',re.MULTILINE|re.IGNORECASE)


def stage_key(stage):
    if stage=='m3_ir':return (0,0)
    if stage=='m4_repair_parse':return (1,1)
    if stage.startswith('m4_repair_parse_'):return (1,int(stage.rsplit('_',1)[1]))
    return (2,int(stage.rsplit('_',1)[1]))


def positive_integer(value):return isinstance(value,int) and not isinstance(value,bool) and value>=0


def inventory(manifest,available_stages,method,maximum):
    """Use recorded call order; file-name order is only an unresolved fallback."""
    raw=manifest.get('usage',{});logged=raw.get('per_stage') if isinstance(raw,dict) else None
    issues=[];rows=[];known=[]
    if isinstance(logged,list) and len(logged)>maximum:raise ValueError('stage_metadata_inspection_limit')
    if not isinstance(logged,list) or not logged:
        issues.append('recorded_call_order_unavailable');logged=[]
    for index,entry in enumerate(logged):
        if not isinstance(entry,dict) or not isinstance(entry.get('stage'),str) or not STAGE_RE.fullmatch(entry['stage']):
            issues.append('unknown_or_malformed_recorded_stage');continue
        stage=entry['stage'];known.append(stage)
        usage=entry.get('usage') if isinstance(entry.get('usage'),dict) else {}
        rows.append({'stage':stage,'recorded_call_index':index,'order_source':'usage.per_stage',
            'reported_finish_reason':entry.get('finish_reason') if isinstance(entry.get('finish_reason'),str) else None,
            'recorded_usage':{k:usage[k] if positive_integer(usage.get(k)) else None for k in ('prompt_tokens','completion_tokens','total_tokens','reasoning_tokens')},
            'reported_latency_s':entry.get('latency_s') if isinstance(entry.get('latency_s'),(int,float)) and not isinstance(entry.get('latency_s'),bool) else None})
    if len(known)!=len(set(known)):issues.append('repeated_stage_name_raw_history_ambiguous')
    allowed={s for s in available_stages if STAGE_RE.fullmatch(s)}
    if set(available_stages)-allowed:issues.append('unrecognized_saved_response_files')
    extra=allowed-set(known)
    if extra:issues.append('saved_response_without_matching_call_metadata')
    if 'm3_ir' not in known and not logged:extra.add('m3_ir')
    for stage in sorted(extra,key=stage_key):
        rows.append({'stage':stage,'recorded_call_index':None,'order_source':'filename_hint_only',
            'reported_finish_reason':None,'recorded_usage':{k:None for k in ('prompt_tokens','completion_tokens','total_tokens','reasoning_tokens')},'reported_latency_s':None})
    if method=='m3' and (any(s!='m3_ir' for s in known) or any(s!='m3_ir' for s in allowed)):
        issues.append('repair_stages_unexpected_for_m3')
    if logged and (not known or known[0]!='m3_ir'):issues.append('initial_generation_not_first_recorded_call')
    if len(rows)>maximum:raise ValueError('response_count_inspection_limit')
    terminal=(known[-1] if known and not issues else None)
    for row in rows:row['is_recorded_terminal']=terminal==row['stage']
    config=manifest.get('model',{})
    requested=config.get('max_tokens') if isinstance(config,dict) else None
    for row in rows:
        row['recorded_requested_max_tokens']=requested if positive_integer(requested) and requested>0 else None
    return {'attempts':rows,'metadata_issues':sorted(set(issues)),
            'terminal_stage':terminal,'terminal_order_status':'resolved' if terminal else 'unresolved',
            'unrecognized_response_file_count':len(set(available_stages)-allowed)}


def schema_result(documents,schema,node_limit):
    if len(documents)!=1:return {'document_state':'multiple_documents' if documents else 'no_documents','schema_error_count':None,'schema_errors':[]}
    document=documents[0]
    if not isinstance(document,dict):return {'document_state':'non_mapping','schema_error_count':None,'schema_errors':[]}
    try:census.validate_json_shape(document,node_limit)
    except (ValueError,TypeError,RecursionError):return {'document_state':'non_json_or_recursive','schema_error_count':None,'schema_errors':[]}
    errors=list(Draft202012Validator(schema).iter_errors(document))
    return {'document_state':'schema_conformant_ir' if not errors else 'mapping_schema_invalid',
            'schema_error_count':len(errors),'schema_errors':[{'path':'/'+ '/'.join(map(str,e.absolute_path)),'validator':e.validator} for e in errors[:30]]}


def candidates(text,maximum):
    spans=[]
    for match in FENCE_RE.finditer(text):
        spans.append(('complete_fence',match.start(1),match.end(1)))
        if len(spans)>maximum:return [],True
    markers=list(MARKER_RE.finditer(text))
    if len(markers)>maximum:return [],True
    for index,match in enumerate(markers):
        if match.group(1).lower() not in ('serviceflow.yaml','serviceflow.yml'):continue
        spans.append(('serviceflow_file_marker',match.end(),markers[index+1].start() if index+1<len(markers) else len(text)))
        if len(spans)>maximum:return [],True
    return spans,False


def analyze_text(raw,metadata,schema,policy):
    record={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'reported_length_stop':metadata.get('reported_finish_reason')=='length',
            'reported_reasoning_tokens':metadata.get('recorded_usage',{}).get('reasoning_tokens'),
            'candidates':[],'candidate_inspection_limited':False,'syntax_end_of_stream_signal':False,
            'semantic_outcome':'not_measured','extraction_repair_performed':False}
    completion=metadata.get('recorded_usage',{}).get('completion_tokens');requested=metadata.get('recorded_requested_max_tokens')
    record['completion_equals_recorded_requested_limit']=(completion==requested if completion is not None and requested is not None else None)
    if len(raw)>policy['max_response_bytes']:record['text_state']='inspection_limit';return record
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:record['text_state']='invalid_utf8';return record
    record['characters']=len(text)
    if not raw:record['text_state']='empty_content';return record
    if not text.strip():record['text_state']='whitespace_only';return record
    try:
        documents,error=extract_yaml_documents(text)
    except (ValueError,TypeError,RecursionError):
        documents,error=[],'non_json_or_recursive'
    if error:
        # A syntax symptom is not proof of a provider truncation; the finish
        # metadata is reported separately. Do not copy instance text/errors.
        end=bool(re.search(r'end of stream|unexpected end|while scanning a quoted scalar',str(error),re.IGNORECASE))
        record['syntax_end_of_stream_signal']=end
        state='no_documents' if 'no YAML documents found' in str(error) else 'parse_error_end_of_stream' if end else 'parse_error_other'
        legacy={'document_state':state,'schema_error_count':None,'schema_errors':[]}
    else:legacy=schema_result(documents,schema,policy['max_document_nodes'])
    record['legacy']=legacy
    record['text_state']=legacy['document_state']
    spans,limited=candidates(text,policy['max_presentation_candidates'])
    record['candidate_inspection_limited']=limited
    for kind,start,end in spans:
        content=text[start:end]
        try:
            parsed=[doc for doc in yaml.safe_load_all(content) if doc is not None]
            assessment=schema_result(parsed,schema,policy['max_document_nodes'])
        except (yaml.YAMLError,ValueError,TypeError,RecursionError):continue
        if assessment['document_state']=='schema_conformant_ir':
            record['candidates'].append({'kind':kind,'character_start':start,'character_end':end,
                'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'structural_schema_only':True})
    # This records a possible *presentation* extraction, not an approved
    # parser repair. Two spans remain ambiguous even if their bytes match.
    record['wrapper_observation']=('candidate_inspection_limited' if limited else 'multiple_complete_ir_candidates' if len(record['candidates'])>1 else
        'legacy_already_schema_conformant' if legacy['document_state']=='schema_conformant_ir' else
        'one_complete_explicit_ir_candidate' if len(record['candidates'])==1 else 'no_complete_explicit_ir_candidate')
    return record


def summarize(records):
    groups={}
    for record in records:
        source=record['source'];key=(source['model'],source['method'])
        row=groups.setdefault(key,{'model':key[0],'method':key[1],'declared_cells':0,'audit_states':Counter(),
            'terminal_text_states':Counter(),'attempt_text_states':Counter(),'reported_finish_reasons':Counter(),
            'wrapper_observations':Counter(),'length_stop_cells':0,'order_unresolved_cells':0})
        row['declared_cells']+=1;row['audit_states'][record['state']]+=1
        row['order_unresolved_cells']+=record.get('terminal_order_status')!='resolved'
        attempts=record.get('attempts',[])
        row['length_stop_cells']+=any(a.get('reported_length_stop') for a in attempts)
        for attempt in attempts:
            row['attempt_text_states'][attempt['text_state']]+=1
            row['reported_finish_reasons'][str(attempt.get('reported_finish_reason'))]+=1
            row['wrapper_observations'][attempt.get('wrapper_observation','not_inspected')]+=1
        terminal=next((a for a in attempts if a.get('is_recorded_terminal')),None)
        row['terminal_text_states'][terminal['text_state'] if terminal else
            'terminal_uninspected_due_to_audit_error' if record['state']=='inspection_error' else 'terminal_order_unresolved']+=1
    counters=('audit_states','terminal_text_states','attempt_text_states','reported_finish_reasons','wrapper_observations')
    return [{**row,**{k:dict(row[k]) for k in counters}} for _,row in sorted(groups.items())]
