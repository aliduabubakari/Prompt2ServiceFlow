"""Versioned public-contract mock compiler correction, independent of gold.

The model's IR and service/binding choices are immutable inputs. This module
can read only inventoried public catalog descriptors and artifact schemas.
Examples are deterministic public-contract mock values, never service results.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path,PurePosixPath
import shutil

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
import scenario_alignment_v2 as metadata
import audit_v2_output_trace as trace
from prompt2serviceflow.experiments import runtime_compiler as original

VERSION='p2sf.public-output-contract-mock/2.0.0'


def unique(items,key):
    result={item[key]:item for item in items}
    if len(result)!=len(items):raise ValueError('Duplicate '+key)
    return result


class PublicWorkspace:
    def __init__(self,root):
        self.root=Path(root).resolve();self.manifest=metadata.document(self.root/'workspace.yaml')
        self.inventory=unique(self.manifest['files'],'path');self.used={str(self.root/'workspace.yaml'):metadata.sha(self.root/'workspace.yaml')};self.cache={}
        self.index=self.read('catalog/catalog.yaml')
        self.services={(s['service_id'],s['version']):s for s in self.index['services']}
        if len(self.services)!=len(self.index['services']):raise ValueError('Duplicate catalog service/version')

    def read(self,relative):
        if '..' in PurePosixPath(relative).parts or PurePosixPath(relative).is_absolute():raise ValueError('Noncanonical public path')
        if not relative.startswith(('catalog/','contracts/')):raise ValueError('Compiler may read public catalog/contracts only')
        if relative not in self.inventory:raise ValueError('Public source is absent from workspace inventory: '+relative)
        path=metadata.bounded.safe(self.root,relative)
        expected=self.inventory[relative]['sha256']
        if metadata.sha(path)!=expected:raise ValueError('Public source hash changed: '+relative)
        self.used[str(path)]=expected
        if relative not in self.cache:self.cache[relative]=metadata.document(path)
        return copy.deepcopy(self.cache[relative])

    def descriptor(self,service,version):
        item=self.services.get((service,version))
        if item is None:raise ValueError('Bound service/version missing from public catalog')
        relative='catalog/'+item['descriptor_path'];value=self.read(relative)
        if (value['service_id'],value['version'])!=(service,version):raise ValueError('Descriptor identity mismatch')
        return value,relative

    def check_pin(self,ir):
        pin=ir['catalog_snapshot'];actual=self.manifest['catalog']
        allowed={actual['pinned_catalog_yaml_sha256'],actual.get('sanitized_catalog_yaml_sha256')}
        if pin['version']!=actual['version'] or pin['sha256'] not in allowed or not pin['sha256']:
            raise ValueError('Saved IR and public catalog pin differ')


def no_references(schema):
    stack=[schema]
    while stack:
        value=stack.pop()
        if isinstance(value,dict):
            if any(k in value for k in ('$ref','$dynamicRef','$recursiveRef')):raise ValueError('Referenced schemas need a separate local resolver; no remote resolution allowed')
            stack.extend(value.values())
        elif isinstance(value,list):stack.extend(value)


def validators(schemas):
    result=[]
    for schema in schemas:
        no_references(schema);Draft202012Validator.check_schema(schema)
        result.append(Draft202012Validator(schema,format_checker=FormatChecker()))
    return result


def public_example(schemas,depth=0):
    """Deterministic examples from public constraints; no private targets.

    Retain the old example policy, with conjunction handling for public local
    artifact and service-port contracts. Unsupported schemas fail closed.
    """
    if depth>32:raise ValueError('Public example depth limit')
    checks=validators(schemas);candidates=[]
    for schema in schemas:
        try:candidates.append(original._schema_example(schema))
        except (ValueError,TypeError,KeyError,RecursionError):pass
    flattened=[]
    for schema in schemas:
        if 'allOf' in schema:
            flattened.extend(schema['allOf']);flattened.append({k:v for k,v in schema.items() if k!='allOf'})
        else:flattened.append(schema)
    object_schemas=[s for s in flattened if s.get('type')=='object' or 'properties' in s]
    if object_schemas:
        names=sorted({n for s in object_schemas for n in s.get('required',[])})
        for name in ['success','errors']:
            if any(name in s.get('properties',{}) for s in object_schemas) and name not in names:names.append(name)
        try:
            candidates.append({name:public_example([s['properties'][name] for s in object_schemas if name in s.get('properties',{})] or [{}],depth+1) for name in names})
        except ValueError:pass
    arrays=[s for s in flattened if s.get('type')=='array']
    if arrays:
        count=max(s.get('minItems',0) for s in arrays)
        if 0<=count<=100:
            try:candidates.append([public_example([s.get('items',{}) for s in arrays],depth+1) for _ in range(count)])
            except (ValueError,TypeError):pass
    if flattened!=schemas:
        try:candidates.append(public_example(flattened,depth+1))
        except ValueError:pass
    for candidate in candidates:
        try:json.dumps(candidate,allow_nan=False)
        except (TypeError,ValueError):continue
        if all(check.is_valid(candidate) for check in checks):return candidate
    raise ValueError('No supported deterministic example satisfies all public output schemas')


def output_schemas(public,binding,artifact,port):
    descriptor,path=public.descriptor(binding['service_id'],binding['service_version'])
    ports=[p for p in descriptor.get('interface',{}).get('outputs',[]) if p['name']==port]
    if len(ports)!=1:raise ValueError('Output port unavailable or ambiguous')
    public_port=ports[0];schemas=[];sources=[]
    local=artifact.get('schema_ref')
    if local:
        if not local.startswith('contracts/'):raise ValueError('Artifact schema must be an inventoried public contracts path')
        schemas.append(public.read(local));sources.append({'path':local,'kind':'artifact_schema'})
    for rule in descriptor.get('contracts',[]):
        if rule.get('type')=='json_schema' and rule.get('applies_to')=='output' and rule.get('target')==port:
            expression=rule.get('expression')
            if not expression:continue
            schema=json.loads(expression) if isinstance(expression,str) else copy.deepcopy(expression)
            if not isinstance(schema,dict):raise ValueError('Output JSON-schema expression must be an object')
            schemas.append(schema);sources.append({'path':path,'kind':'service_output_schema','contract_id':rule.get('contract_id'),'port':port})
    return schemas,sources,public_port


def corrected_spec(spec,artifact,binding,port,public):
    before=copy.deepcopy(spec)
    try:
        schemas,sources,public_port=output_schemas(public,binding,artifact,port)
        if not schemas:return before,{'state':'unchanged_no_concrete_schema','sources':sources}
        checks=validators(schemas)
        if 'json_value' in before and all(v.is_valid(before['json_value']) for v in checks):
            state='corrected_json_null_serialization' if before['json_value'] is None else 'unchanged_valid_public_example'
            return before,{'state':state,'sources':sources,'public_schema_count':len(schemas)}
        media=public_port.get('media_type') or artifact.get('media_type')
        if media and media!='application/json' and not media.endswith('+json'):
            return before,{'state':'unchanged_non_json_contract','sources':sources}
        after=copy.deepcopy(before);after['json_value']=public_example(schemas)
        return after,{'state':'corrected_from_public_output_contract','sources':sources,'public_schema_count':len(schemas)}
    except (ValueError,TypeError,KeyError,SchemaError) as exc:
        # Preserve the baseline output, and expose unsupported correction.
        return before,{'state':'unchanged_unsupported_public_contract','reason':str(exc)[:700]}


def render(specs):
    # JSON null is a valid public example, even though its Python value is None.
    return original._script_text(specs).replace('if output.get("json_value") is not None:', 'if "json_value" in output:')


def writer(spec,intent):
    item=trace.planned_output(spec)
    if 'json_value' in spec:item={**item,'path':f"artifacts/{spec['artifact_id']}.json",'kind':'public_contract_json_example','literal_json_value':spec['json_value']}
    return {**item,'intent_id':intent}


def compile_plan(submission,public):
    submission=Path(submission);ir=metadata.document(submission/'serviceflow.yaml');public.check_pin(ir)
    runtime=metadata.document(submission/'runtime/manifest.yaml')
    scanned=trace.scan_runtime(submission,runtime,2097152)
    if not scanned['complete_recognized_writer_plan']:raise ValueError('Only the frozen mock compiler template is eligible')
    artifacts=unique(ir['artifacts'],'artifact_id');bindings=unique(ir['bindings'],'intent_id')
    scripts=[];records=[];writers=[]
    for task,recognized in zip(runtime['tasks'],scanned['scripts']):
        specs=[];binding=bindings.get(task['intent_id'])
        for before in recognized['outputs']:
            name=before['artifact_id'];artifact=artifacts.get(name)
            ports=[p['port'] for p in (binding or {}).get('output_bindings',[]) if p['artifact_id']==name]
            if artifact is None or binding is None or len(ports)!=1:
                after=copy.deepcopy(before);record={'state':'unchanged_unresolved_model_binding'}
            else:after,record=corrected_spec(before,artifact,binding,ports[0],public)
            specs.append(after);writers.append(writer(after,task['intent_id']))
            records.append({'intent_id':task['intent_id'],'artifact_id':name,'before':before,'after':after,**record})
        original_path=trace.local(submission/'runtime',task['script']);original_text=original_path.read_text()
        changed=specs!=recognized['outputs'] or any('json_value' in s and s['json_value'] is None for s in specs)
        scripts.append({'path':task['script'],'source_sha256':metadata.sha(original_path),
                        'text':render(specs) if changed else original_text,'changed':changed})
    return {'compiler_version':VERSION,'source_ir_sha256':metadata.sha(submission/'serviceflow.yaml'),
        'source_runtime_sha256':metadata.sha(submission/'runtime/manifest.yaml'),'runtime':runtime,
        'scripts':scripts,'writers':writers,'outputs':records,'public_inputs':dict(public.used),
        'changed_scripts':sum(s['changed'] for s in scripts),
        'scope':'Recompiled public-contract mock examples. Same IR, bindings and parameters; public schemas only. No private assertions, reference IR or model calls used in compilation.'}


def materialize(plan,submission,destination):
    submission=Path(submission);destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    if metadata.sha(submission/'serviceflow.yaml')!=plan['source_ir_sha256'] or metadata.sha(submission/'runtime/manifest.yaml')!=plan['source_runtime_sha256']:raise ValueError('Saved source changed')
    shutil.copyfile(submission/'serviceflow.yaml',destination/'serviceflow.yaml')
    (destination/'runtime').mkdir();(destination/'runtime/manifest.yaml').write_text(json.dumps(plan['runtime'],indent=2)+'\n')
    for script in plan['scripts']:
        if metadata.sha(trace.local(submission/'runtime',script['path']))!=script['source_sha256']:raise ValueError('Original script changed')
        path=trace.local(destination/'runtime',script['path']);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(script['text'])
    if metadata.sha(destination/'serviceflow.yaml')!=plan['source_ir_sha256']:raise ValueError('IR bytes changed')
