"""General static findings, separate from any family-specific execution adapter.

No service dispatch, private answers, expression evaluation, mock values, or
network resolution. Context/semantic signals are review cues, not proof that
a descriptor is sufficient or a model output is wrong.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator

CATEGORIES = ('saved_structure', 'catalog_contract', 'dataflow', 'frozen_type_rule',
              'input_context', 'execution_context', 'runtime_semantics', 'inspection_error')
HARD = {'saved_structure', 'catalog_contract', 'dataflow'}


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '://' in relative:
        raise ValueError('Only contained local references are inspected')
    path = (root / relative).resolve()
    if '..' in Path(relative).parts or not path.is_relative_to(root.resolve()):
        raise ValueError('Reference escapes public workspace')
    return path


def validate_json_shape(value, maximum):
    """Reject cycles, non-JSON YAML values/keys, and excessive traversal."""
    stack, active, count = [(value, False)], set(), 0
    while stack:
        node, leaving = stack.pop()
        if leaving:
            active.remove(id(node)); continue
        count += 1
        if count > maximum:
            raise ValueError('node_limit')
        if isinstance(node, (dict, list)):
            if id(node) in active:
                raise ValueError('recursive_alias')
            if isinstance(node, dict) and any(not isinstance(k, str) for k in node):
                raise ValueError('non_string_mapping_key')
            active.add(id(node)); stack.append((node, True))
            stack.extend((v, False) for v in (node.values() if isinstance(node, dict) else node))
    json.dumps(value, allow_nan=False)


def template_value(value):
    if isinstance(value, str):
        return any(marker in value for marker in ('{{', '${', '{workspace}', '{fixtures}'))
    if isinstance(value, list):
        return any(template_value(v) for v in value)
    if isinstance(value, dict):
        return any(template_value(v) for v in value.values())
    return False


def fixture_presence(reference, workspace, scenarios):
    """Report literal and active-scenario presence separately; never choose."""
    result = {'literal_state': 'unmapped', 'active_scenario_state': 'unmapped', 'scenarios': []}
    if not isinstance(reference, str) or not reference:
        result['literal_state'] = 'no_reference'; return result
    try:
        literal = safe_path(workspace, reference)
        result['literal_state'] = 'file' if literal.is_file() else 'directory' if literal.is_dir() else 'missing'
    except (ValueError, OSError):
        result['literal_state'] = 'nonlocal_or_unsafe'; return result
    parts = Path(reference).parts
    if parts[:2] == ('fixtures','inputs') and len(parts)>2:
        relative = Path(*parts[2:]).as_posix()
    elif parts[:2] == ('fixtures','scenarios') and len(parts)>3:
        relative = Path(*parts[3:]).as_posix()
    else:
        return result
    for scenario in scenarios:
        try:
            root = safe_path(workspace, scenario['fixture_root'])
            path = safe_path(root, relative)
            state = 'file' if path.is_file() else 'directory' if path.is_dir() else 'missing'
        except (ValueError, OSError, KeyError):
            state = 'mapping_error'
        result['scenarios'].append({'scenario':scenario['name'], 'state':state})
    states = [s['state'] for s in result['scenarios']]
    result['active_scenario_state'] = 'all_files' if states and all(s=='file' for s in states) else 'not_all_files' if states else 'no_scenarios'
    return result


def schema_review(reference, workspace, load, maximum):
    try:
        path = safe_path(workspace, reference)
        if not path.is_file(): return {'state':'missing_public_schema'}
        if path.stat().st_size>maximum: return {'state':'schema_inspection_limit'}
        value=load(path); validate_json_shape(value,100000)
        Draft202012Validator.check_schema(value)
        stack=[value]; refs=0
        while stack:
            node=stack.pop()
            if isinstance(node,dict):
                refs+=sum(k in node for k in ('$ref','$dynamicRef')); stack.extend(node.values())
            elif isinstance(node,list): stack.extend(node)
        return {'state':'reference_resolution_needed' if refs else 'syntax_checked_only', 'reference_count':refs,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    except (ValueError,TypeError,OSError,RecursionError):
        return {'state':'unmapped_or_invalid_public_schema'}
    except Exception as exc:
        return {'state':'schema_inspection_error','error_type':type(exc).__name__}


def descriptor_signals(descriptor):
    interface=descriptor.get('interface',{}); parameters=interface.get('parameters',[])
    ports=[*interface.get('inputs',[]),*interface.get('outputs',[])]
    wording=' '.join(map(str,[descriptor.get('capability',{}).get('summary',''),*descriptor.get('capability',{}).get('operations',[])])).lower()
    policies=descriptor.get('policies',{})
    return {
        'profile_parameter_without_enum': any(p.get('name')=='operation_profile' and 'enum' not in p for p in parameters),
        'opaque_object_parameters': sorted(p['name'] for p in parameters if p.get('type') in ('object','array') and 'enum' not in p),
        'any_data_ports': sorted(p['name'] for p in ports if p.get('data_type')=='any'),
        'many_artifact_ports': sorted(p['name'] for p in ports if p.get('cardinality')=='many' and p.get('channel')=='artifact'),
        'ports_without_schema_ref': sum(not p.get('schema_ref') for p in ports),
        'declared_contract_count': len(descriptor.get('contracts',[])),
        'generic_reviewed_operation_wording': bool(re.search(r'perform the reviewed|reviewed input artifacts|reviewed multimodal batch operation',wording)),
        'network_required': policies.get('network_access')=='required',
        'credentials_required': policies.get('secret_access')=='required' or any(p.get('required') is True for p in interface.get('secrets',[])),
        'destructive_wording_review': bool(re.search(r'\bdelete\b|\bdeletes\b|\bdeletion\b|\btruncate\b|\bcleanup\b|\bremove\b|\bdrop\b',wording)),
        'runtime_image_declared': bool(descriptor.get('invocation',{}).get('image')),
        'implementation_ref_declared': bool(descriptor.get('invocation',{}).get('implementation_ref')),
        'mock_supported': descriptor.get('invocation',{}).get('mock_supported') is True,
        'semantic_sufficiency':'not_established_by_static_signals',
    }


def analyze(ir, *, schema, catalog_get, workspace, scenarios, load, maximum=2097152, node_limit=100000):
    findings, services, inputs, schemas = [], [], [], []
    def add(category,code,subject,**details):
        findings.append({'category':category,'code':code,'subject':str(subject),**details})
    if not isinstance(ir,dict):
        add('saved_structure','document_not_object','document'); return result('invalid_document',findings,services,inputs,schemas)
    try: validate_json_shape(ir,node_limit)
    except (ValueError,TypeError,RecursionError):
        add('saved_structure','non_json_or_recursive_document','document'); return result('invalid_document',findings,services,inputs,schemas)
    for error in Draft202012Validator(schema).iter_errors(ir):
        add('saved_structure','ir_schema_violation','/'+ '/'.join(map(str,error.absolute_path)),validator=error.validator)

    def section(name,key):
        rows=ir.get(name)
        if not isinstance(rows,list): add('saved_structure','section_not_list',name); return [],{}
        valid=[]; mapped={}
        for index,row in enumerate(rows):
            if not isinstance(row,dict) or not isinstance(row.get(key),str):
                add('saved_structure','invalid_section_entry',f'{name}/{index}'); continue
            valid.append(row)
            if row[key] in mapped: add('saved_structure','duplicate_identifier',f'{name}/{index}')
            else: mapped[row[key]]=row
        return valid,mapped
    _,intents=section('service_intents','intent_id'); bindings,bmap=section('bindings','intent_id'); _,artifacts=section('artifacts','artifact_id')
    for identity in sorted(set(intents)^set(bmap)): add('saved_structure','intent_binding_roster_mismatch',identity)
    parents={i:set() for i in intents}; writers=defaultdict(list)
    for index,binding in enumerate(bindings):
        intent=binding['intent_id']; subject=f'bindings/{index}:{intent}'
        name,version=binding.get('service_id'),binding.get('service_version'); descriptor=None
        if isinstance(name,str) and isinstance(version,str):
            try:
                descriptor,error=catalog_get(name,version)
                if error: add('catalog_contract' if error=='service_version_absent_from_public_catalog' else 'inspection_error',error,subject)
            except Exception as exc: add('inspection_error','catalog_inspection_error',subject,error_type=type(exc).__name__)
        else: add('saved_structure','invalid_service_identity',subject)
        service={'service_id':name,'service_version':version,'intent_id':intent,'public_descriptor_available':descriptor is not None}
        if descriptor:
            service['descriptor_fingerprint']=hashlib.sha256(json.dumps(descriptor,sort_keys=True,default=str).encode()).hexdigest()
            service['signals']=descriptor_signals(descriptor)
            signals=service['signals']
            for flag in ('profile_parameter_without_enum','generic_reviewed_operation_wording'):
                if signals[flag]: add('runtime_semantics',flag,subject)
            if signals['opaque_object_parameters']: add('runtime_semantics','object_parameter_fields_unspecified',subject,parameter_names=signals['opaque_object_parameters'])
            if signals['any_data_ports']: add('runtime_semantics','any_port_payload_shape_unspecified',subject,port_names=signals['any_data_ports'])
            for flag in ('network_required','credentials_required','destructive_wording_review'):
                if signals[flag]: add('execution_context',flag,subject)
        services.append(service); interface=descriptor.get('interface',{}) if descriptor else {}
        bound_sets={}
        for field,declared_list in [('input_bindings',interface.get('inputs',[])),('output_bindings',interface.get('outputs',[]))]:
            raw=binding.get(field)
            if not isinstance(raw,list): add('saved_structure','port_bindings_not_list',subject+'/'+field); raw=[]
            rows=[p for p in raw if isinstance(p,dict) and isinstance(p.get('port'),str) and isinstance(p.get('artifact_id'),str)]
            if len(rows)!=len(raw): add('saved_structure','malformed_port_binding',subject+'/'+field)
            bound_sets[field]={p['artifact_id'] for p in rows}
            by_name={p['name']:p for p in declared_list}; counts=Counter(p['port'] for p in rows)
            if descriptor:
                for port,definition in by_name.items():
                    if definition.get('required') is True and not counts[port]: add('catalog_contract','required_port_unbound',subject+'/'+field+'/'+port)
                for port,count in counts.items():
                    if port not in by_name: add('catalog_contract','unknown_service_port',subject+'/'+field+'/'+port)
                    elif count>1 and by_name[port].get('cardinality')=='one': add('catalog_contract','single_port_bound_multiple_times',subject+'/'+field+'/'+port)
            for port in rows:
                identity=port['artifact_id']; where=subject+'/'+field+'/'+identity; artifact=artifacts.get(identity)
                if artifact is None: add('dataflow','bound_artifact_undeclared',where); continue
                definition=by_name.get(port['port'],{})
                if definition.get('data_type') and artifact.get('data_type') and definition['data_type']!=artifact['data_type']:
                    add('frozen_type_rule','port_data_type_not_exact',where,port_type=definition['data_type'],artifact_type=artifact['data_type'])
                producer=artifact.get('producer'); producers=producer if isinstance(producer,list) else [producer] if producer else []
                if field=='output_bindings':
                    writers[identity].append(intent)
                    if intent not in producers: add('dataflow','writer_producer_mismatch',where)
                elif producers:
                    for parent in producers:
                        if not isinstance(parent,str) or parent not in parents: add('dataflow','unknown_artifact_producer',where)
                        elif intent in parents: parents[intent].add(parent)
                    if isinstance(producer,list): add('execution_context','declared_producer_merge_needs_semantics',where)
                else:
                    external=artifact.get('external_system_ref')
                    row={'intent_id':intent,'artifact_id':identity,'port':port['port'],'kind':artifact.get('kind'),
                         'port_channel':definition.get('channel'),'external_system_declared':bool(external)}
                    reference=artifact.get('fixture_ref')
                    if not reference:
                        row['state']='external_input_link_unspecified'
                        add('input_context',row['state'],where,kind=artifact.get('kind'),external_system_declared=bool(external))
                    else:
                        row['presence']=fixture_presence(reference,workspace,scenarios)
                        presence=row['presence']
                        if presence['literal_state']=='file' and presence['active_scenario_state']=='all_files': row['state']='literal_and_active_files_present'
                        elif presence['active_scenario_state']=='all_files': row['state']='active_files_present_literal_differs'
                        elif presence['literal_state']=='file': row['state']='literal_file_present_runtime_mapping_review'
                        else: row['state']='no_resolved_public_file'
                        if row['state'] not in ('literal_and_active_files_present','active_files_present_literal_differs'):
                            add('input_context',row['state'],where,literal_state=presence['literal_state'],active_scenario_state=presence['active_scenario_state'])
                    inputs.append(row)
        if intent in intents:
            for declared_key,field in [('inputs','input_bindings'),('outputs','output_bindings')]:
                declared=intents[intent].get(declared_key)
                if isinstance(declared,list) and all(isinstance(v,str) for v in declared) and set(declared)!=bound_sets[field]:
                    add('catalog_contract','intent_binding_artifact_set_mismatch',subject+'/'+declared_key)
        parameters=binding.get('parameter_bindings')
        if not isinstance(parameters,dict): add('saved_structure','parameters_not_object',subject); parameters={}
        declarations={p['name']:p for p in interface.get('parameters',[])}
        if descriptor:
            for key,definition in declarations.items():
                if key not in parameters:
                    if definition.get('required') is True: add('catalog_contract','required_parameter_absent',subject+'/'+key)
                    continue
                if template_value(parameters[key]):
                    add('execution_context','parameter_template_needs_runtime_context',subject+'/'+key); continue
                constraint={k:definition[k] for k in ('type','enum','minimum','maximum','pattern') if k in definition}
                try:
                    for error in Draft202012Validator(constraint).iter_errors(parameters[key]):
                        add('catalog_contract','parameter_constraint_violation',subject+'/'+key,validator=error.validator)
                except Exception as exc: add('inspection_error','parameter_constraint_inspection_error',subject+'/'+key,error_type=type(exc).__name__)
            for key in set(parameters)-set(declarations): add('catalog_contract','unknown_parameter',subject+'/'+key)
            declarations={p['name']:p for p in interface.get('secrets',[])}
            raw=binding.get('secret_bindings',[])
            mapped={p['secret'] for p in raw if isinstance(p,dict) and isinstance(p.get('secret'),str)} if isinstance(raw,list) else set()
            for key,definition in declarations.items():
                if definition.get('required') is True and key not in mapped: add('catalog_contract','required_secret_unbound',subject+'/'+key)
            for key in mapped-set(declarations): add('catalog_contract','unknown_secret_binding',subject+'/'+key)
            if mapped: add('execution_context','secret_resolution_required',subject)

    for identity,artifact in artifacts.items():
        producer=artifact.get('producer'); declared=producer if isinstance(producer,list) else [producer] if producer else []
        actual=writers[identity]
        if len(actual)>1:
            names=[p for p in declared if isinstance(p,str)]
            valid_merge=isinstance(producer,list) and len(names)==len(declared) and len(set(actual))==len(actual) and set(actual)==set(names)
            add('execution_context' if valid_merge else 'dataflow','multiple_bound_writers',identity)
        for name in declared:
            if name not in actual: add('dataflow','declared_producer_has_no_output_binding',identity)
        if artifact.get('schema_ref'):
            review=schema_review(artifact['schema_ref'],workspace,load,maximum); schemas.append({'artifact_id':identity,**review})
            if review['state']!='syntax_checked_only': add('inspection_error' if review['state']=='schema_inspection_error' else 'runtime_semantics','artifact_schema_'+review['state'],identity)
    flow=ir.get('control_flow')
    if not isinstance(flow,dict): add('saved_structure','control_flow_not_object','control_flow'); flow={}
    edges=flow.get('edges',[])
    if not isinstance(edges,list): add('saved_structure','edges_not_list','control_flow'); edges=[]
    for index,edge in enumerate(edges):
        where='control_flow/edges/'+str(index)
        if not isinstance(edge,dict) or not isinstance(edge.get('from'),str) or not isinstance(edge.get('to'),str):
            add('dataflow','malformed_control_edge',where); continue
        if edge['from'] not in parents or edge['to'] not in parents: add('dataflow','unknown_control_endpoint',where)
        else: parents[edge['to']].add(edge['from'])
        if edge.get('condition'): add('execution_context','condition_expression_requires_semantics',where)
    for field in ('branches','gates','parallel_groups'):
        if flow.get(field): add('execution_context','declared_'+field+'_requires_runtime_semantics','control_flow/'+field)
    pending,done=set(parents),set()
    while pending:
        ready={i for i in pending if parents[i].issubset(done)}
        if not ready: add('dataflow','dependency_cycle','control_flow'); break
        pending-=ready; done|=ready
    return result('inspected',findings,services,inputs,schemas)


def result(state,findings,services,inputs,schemas):
    return {'state':state,'findings':findings,'finding_counts':dict(Counter(f['category'] for f in findings)),
            'services':services,'external_inputs':inputs,'artifact_schemas':schemas,
            'execution_ready':False,'semantic_outcome':'not_measured','public_gates':'not_remeasured'}


def family_groups(references):
    """Reference-only service-set groups; scores/model records are not inputs."""
    groups={}
    for reference in references:
        analysis=reference['analysis']
        roster=sorted({s['service_id']+'@'+s['service_version'] for s in analysis.get('services',[])
                       if isinstance(s.get('service_id'),str) and isinstance(s.get('service_version'),str)})
        identity=hashlib.sha256(json.dumps(roster).encode()).hexdigest()[:16]
        group=groups.setdefault(identity,{'family_id':identity,'services':roster,'reference_cases':[],
            'reference_review_count':0,'external_execution_review_count':0,'reference_input_review_count':0,'schema_reference_review_count':0})
        group['reference_cases'].append(reference['case'])
        group['reference_review_count']+=analysis['state']!='inspected' or any(f['category'] in HARD|{'frozen_type_rule','inspection_error'} for f in analysis['findings']) or not roster
        group['external_execution_review_count']+=sum(any(s.get('signals',{}).get(flag) for flag in ('network_required','credentials_required','destructive_wording_review')) for s in analysis.get('services',[]))
        group['reference_input_review_count']+=sum(i.get('state') not in ('literal_and_active_files_present','active_files_present_literal_differs') for i in analysis.get('external_inputs',[]))
        group['schema_reference_review_count']+=sum(s['state']!='syntax_checked_only' for s in analysis.get('artifact_schemas',[]))
    rows=list(groups.values())
    rows.sort(key=lambda g:(g['reference_review_count'],g['external_execution_review_count'],g['reference_input_review_count'],-len(g['reference_cases']),len(g['services']),g['schema_reference_review_count'],g['family_id']))
    for position,row in enumerate(rows,1):
        row.update(rank=position,reference_pipeline_count=len(row['reference_cases']),unique_service_count=len(row['services']),
                   selection_scope='public_reference_review_only_not_execution_authorization')
        row['reference_cases'].sort()
    return rows
