"""Publicly registered execution-evidence profile layered on compiler v2.

No model/pipeline switches, assertion predicates or reference answers enter
the compiler. Actual public files and declared dependencies drive telemetry.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import public_output_runtime as previous
import execution_evidence_kernel_v2 as kernel

VERSION='p2sf.file-backed-execution-evidence/1.0.1'


def stable_topology(tasks):
    by_id=previous.unique(tasks,'intent_id');ordered=[];done=set()
    while len(ordered)<len(tasks):
        candidates=[t for t in tasks if t['intent_id'] not in done and set(t.get('dependencies',[]))<=done]
        if not candidates:raise ValueError('Unresolved/cyclic task dependency graph')
        task=candidates[0];ordered.append(copy.deepcopy(task));done.add(task['intent_id'])
    return ordered


def fixture_inventory(public,instance):
    result={}
    for relative,item in public.inventory.items():
        if not relative.startswith('fixtures/'):continue
        path=previous.metadata.bounded.safe(public.root,relative)
        reference=previous.metadata.bounded.safe(Path(instance),relative)
        if previous.metadata.sha(path)!=item['sha256'] or not reference.is_file() or previous.metadata.sha(reference)!=item['sha256']:
            raise ValueError('Public/reviewed fixture bytes differ: '+relative)
        result[relative.removeprefix('fixtures/')]=item['sha256']
    return result


def example_observation():
    return {'profile_version':'fixture-execution-evidence/1','success':True,'errors':[],
        'task':'example','fixture':{'file_count':0,'record_count':0,'files':[],'configuration_files':[]},
        'upstream_artifact_count':0,'upstream_artifacts':[]}


def eligible(record,artifact,binding,port,public,profile):
    spec=record['after']
    if spec['data_type'] not in profile['output_data_types']:return False,[], 'outside_registered_types'
    if record['state']=='unchanged_unsupported_public_contract':return False,[],'unsupported_public_contract'
    try:
        schemas,sources,public_port=previous.output_schemas(public,binding,artifact,port)
        if public_port.get('data_type')!=spec['data_type']:return False,schemas,'public_port_type_mismatch'
        descriptor,_=public.descriptor(binding['service_id'],binding['service_version'])
        if descriptor.get('invocation',{}).get('mock_supported') is False:return False,schemas,'mock_explicitly_unsupported'
        media=public_port.get('media_type') or artifact.get('media_type')
        if media and media!='application/json' and not media.endswith('+json'):return False,schemas,'non_json_media'
        if 'json_value' in spec and not isinstance(spec['json_value'],dict):return False,schemas,'non_object_public_value'
        if 'execution_evidence' in (spec.get('json_value') or {}):return False,schemas,'reserved_namespace_collision'
        probe=kernel.evidence_payload(spec,example_observation())
        if not all(v.is_valid(probe) for v in previous.validators(schemas)):return False,schemas,'public_schema_disallows_profile'
        return True,schemas,'registered_execution_evidence'
    except (ValueError,TypeError,KeyError) as exc:return False,[],'unsupported_public_source: '+str(exc)[:200]


def render(specs,task):
    text=previous.render(specs)
    support=Path(kernel.__file__).read_text()
    text=text.replace('def main() -> None:',support+'\n\nPROFILE_TASK = '+repr(task)+'\n\ndef main() -> None:')
    text=text.replace('    for output in OUTPUTS:', '    observation = execution_observation(args, PROFILE_TASK)\n    for output in OUTPUTS:')
    text=text.replace('        if "json_value" in output:',
        '        if output.get("execution_evidence"):\n'
        '            (artifacts / f"{artifact_id}.json").write_text(json.dumps(evidence_payload(output, observation), sort_keys=True) + "\\n", encoding="utf-8")\n'
        '        elif "json_value" in output:')
    text=text.replace('\nif __name__ == "__main__":',
        '\n    write_execution_receipt(args, PROFILE_TASK, OUTPUTS, observation)\n'
        '    if not observation["success"]:\n'
        '        raise RuntimeError("Execution evidence rejected inputs/upstream: " + json.dumps(observation["errors"]))\n'
        '\nif __name__ == "__main__":')
    compile(text,'<registered-execution-evidence>','exec')
    return text


def extend(base,submission,public,instance,profile):
    plan=copy.deepcopy(base);ir=previous.metadata.document(Path(submission)/'serviceflow.yaml')
    artifacts=previous.unique(ir['artifacts'],'artifact_id');bindings=previous.unique(ir['bindings'],'intent_id')
    specs_by_task={};new_writers=[]
    for record in plan['outputs']:
        aid,intent=record['artifact_id'],record['intent_id'];binding=bindings.get(intent)
        ports=[p['port'] for p in (binding or {}).get('output_bindings',[]) if p['artifact_id']==aid]
        if binding is None or aid not in artifacts or len(ports)!=1:
            supported,schemas,reason=False,[],'unresolved_model_binding'
        else:supported,schemas,reason=eligible(record,artifacts[aid],binding,ports[0],public,profile)
        record['profile_state']=reason;record['profile_schemas']=schemas
        if supported:record['after']['execution_evidence']=True
        specs_by_task.setdefault(intent,[]).append(record['after'])
        writer=previous.writer(record['after'],intent)
        if supported:writer={**writer,'path':f'artifacts/{aid}.json','kind':'actual_execution_evidence'};writer.pop('literal_json_value',None)
        writer['visible_path']=writer['path'];writer['path']='execution_artifacts/'+intent+'/'+Path(writer['path']).name
        new_writers.append(writer)
    original_tasks=previous.unique(plan['runtime']['tasks'],'intent_id');scheduling=[]
    for task in plan['runtime']['tasks']:
        dependencies=set(task.get('dependencies',[]))
        for item in (bindings.get(task['intent_id']) or {}).get('input_bindings',[]):
            producers=artifacts[item['artifact_id']].get('producer') or []
            dependencies.update(producers if isinstance(producers,list) else [producers])
        scheduling.append({**task,'dependencies':sorted(dependencies)})
    try:order=stable_topology(scheduling)
    except ValueError as exc:
        blocked=copy.deepcopy(base);blocked['profile_blocked']=str(exc)
        for output in blocked['outputs']:output['profile_state']='blocked_dataflow';output['profile_schemas']=[]
        blocked['public_fixture_root']=str(public.root/'fixtures');blocked['public_fixture_inventory']=fixture_inventory(public,instance)
        blocked['profile_version']=profile['profile_version'];return blocked
    tasks=[copy.deepcopy(original_tasks[t['intent_id']]) for t in order];plans=[]
    for task in tasks:
        intent=task['intent_id'];needed={};errors=[]
        for item in (bindings.get(intent) or {}).get('input_bindings',[]):
            artifact=artifacts[item['artifact_id']]
            producers=artifact.get('producer') or []
            for producer in producers if isinstance(producers,list) else [producers]:
                key=(producer,item['artifact_id']);needed[key]='input_binding'
        for dependency in task.get('dependencies',[]):
            for w in new_writers:
                if w['intent_id']==dependency:needed.setdefault((dependency,w['artifact_id']),'control_dependency')
        upstream=[]
        for (producer,aid),via in sorted(needed.items()):
            writers=[w for w in new_writers if w['intent_id']==producer and w['artifact_id']==aid]
            unique={(w['path'],w['intent_id'],w['artifact_id']) for w in writers}
            if len(unique)!=1:errors.append('Ambiguous/missing declared upstream producer '+producer+'/'+aid);continue
            path,_,_=next(iter(unique));upstream.append({'intent_id':producer,'artifact_id':aid,'path':path,'via':via})
        specs=specs_by_task.get(intent,[])
        definition={'intent_id':intent,'upstream':upstream,'binding_errors':errors,
            'profile_enabled':any(s.get('execution_evidence') for s in specs)}
        original_script=next(s for s in base['scripts'] if s['path']==task['script'])
        plans.append({**original_script,'text':render(specs,definition),'changed':True,'task_evidence':definition})
    plan['runtime']['tasks']=tasks;plan['scripts']=plans;plan['writers']=new_writers;plan['compiler_version']=VERSION
    plan['scheduling_dependencies']={t['intent_id']:t['dependencies'] for t in scheduling}
    plan['changed_scripts']=len(plans);plan['public_inputs']=dict(public.used)
    plan['public_fixture_root']=str(public.root/'fixtures');plan['public_fixture_inventory']=fixture_inventory(public,instance)
    plan['profile_version']=profile['profile_version'];plan['scope']='New file-backed execution-evidence mock profile. Actual public file observations and declared predecessor receipts; no domain outputs/expected values inferred.'
    return plan


def conformance(directory,plan,result,profile):
    checks=[]
    runtime=previous.metadata.document(Path(directory)/'evaluation_runtime.json')
    scenario_definitions={s['name']:s for s in runtime['scenarios']}
    for scenario in result['scenarios']:
        root=Path(directory)/'scenarios'/scenario['scenario']/'snapshot'
        public_fixtures=Path(plan['public_fixture_root'])
        active,_=previous.metadata.fixture_root(public_fixtures.parent,scenario_definitions[scenario['scenario']])
        prefix=active.relative_to(public_fixtures).as_posix();prefix='' if prefix=='.' else prefix+'/'
        visible={name[len(prefix):]:digest for name,digest in plan['public_fixture_inventory'].items() if name.startswith(prefix)}
        for record in plan['outputs']:
            if not record['after'].get('execution_evidence'):continue
            candidates={w['path'] for w in plan['writers'] if w['intent_id']==record['intent_id'] and w['artifact_id']==record['artifact_id']}
            if len(candidates)!=1:
                checks.append({'scenario':scenario['scenario'],'artifact_id':record['artifact_id'],'state':'invalid','errors':['Ambiguous profile writer']});continue
            path=previous.metadata.bounded.safe(root,next(iter(candidates)))
            if not path.is_file():
                # Downstream tasks can be skipped after a declared input failure.
                checks.append({'scenario':scenario['scenario'],'artifact_id':record['artifact_id'],'state':'not_produced_after_execution_failure' if scenario['execution_errors'] else 'missing_profile_output'})
                continue
            try:
                value=json.loads(path.read_text());observation=value['execution_evidence']
                errors=[e.message for v in previous.validators([profile['observation_schema']]) for e in v.iter_errors(observation)]
                errors.extend(e.message for v in previous.validators(record['profile_schemas']) for e in v.iter_errors(value))
                if observation['task']!=record['intent_id']:errors.append('Evidence task identity mismatch')
                fixture=observation['fixture']
                if fixture['file_count']!=len(fixture['files']) or fixture['record_count']!=sum(f['record_count'] for f in fixture['files']):errors.append('Fixture totals inconsistent')
                listed=set()
                for observed in fixture['files']:
                    name=observed['name'];listed.add(name)
                    actual=previous.metadata.bounded.safe(active,name)
                    if visible.get(name)!=observed['sha256'] or kernel.describe_public_file(actual,active)!=observed:errors.append('Fixture observation does not match actual public bytes/counts')
                for configuration in fixture['configuration_files']:
                    listed.add(configuration['name'])
                    if visible.get(configuration['name'])!=configuration['sha256']:errors.append('Fixture configuration digest mismatch')
                listed.update(error['path'] for error in observation['errors'] if 'path' in error)
                if listed!=set(visible):errors.append('Public fixture coverage differs from the visible inventory')
                if observation['upstream_artifact_count']!=len(observation['upstream_artifacts']):errors.append('Upstream totals inconsistent')
                for item in observation['upstream_artifacts']:
                    actual=previous.metadata.bounded.safe(root,item['path'])
                    if not actual.is_file() or previous.metadata.sha(actual)!=item['sha256']:errors.append('Upstream snapshot digest mismatch')
                checks.append({'scenario':scenario['scenario'],'artifact_id':record['artifact_id'],'state':'invalid' if errors else 'valid','errors':errors,'observed_success':observation['success']})
            except (ValueError,KeyError,TypeError) as exc:checks.append({'scenario':scenario['scenario'],'artifact_id':record['artifact_id'],'state':'invalid','errors':[str(exc)]})
    checked=sum(c['state']=='valid' for c in checks)
    return {'checks':checks,'checked':checked,
        'pass':(not checks or checked>0) and all(c['state'] in ('valid','not_produced_after_execution_failure') for c in checks),
        'scope':'Profile conformance only, independent of held-out task assertion pass.'}
