#!/usr/bin/env python3
"""User-run bounded full/compact generation pilot; no semantic execution."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v2_corpus_census as census
import compact_ir
import generation_transport as transport
from prompt2serviceflow.experiments import prompts

controls,replay,parent=census.controls,census.replay,census.parent
CONFIG=ROOT/'audit/v2/generation_pilot.json'
MODELS=ROOT/'audit/v2/generation_models.json'
TESTS=ROOT/'tests/unit/test_v2_generation_pilot.py'
FILES=[Path(__file__).resolve(),CONFIG,MODELS,TESTS,ROOT/'audit/v2/compact_ir.py',ROOT/'audit/v2/generation_transport.py',ROOT/'audit/v2/GENERATION_PILOT.md']


def verify_prompt_inventory(workspace,manifest):
    expected={v['path']:v['sha256'] for v in manifest['files']}
    roots=['task.md','candidates','catalog','schemas','contracts','fixtures']
    for name in roots:
        root=workspace/name
        paths=[root] if root.is_file() else root.rglob('*') if root.is_dir() else []
        for path in paths:
            if not path.is_file():continue
            relative=path.relative_to(workspace).as_posix()
            if (not path.resolve().is_relative_to(workspace.resolve()) or relative not in expected
                    or controls.sha256(path)!=expected[relative]):
                raise ValueError('Uninventoried or changed model-visible public file')


def public_metadata(workspace,manifest,design):
    if controls.sha256(workspace/'task.md')!=manifest['task']['description_sha256']:raise ValueError('Public task checksum changed')
    if controls.sha256(workspace/'catalog/catalog.yaml')!=manifest['catalog']['sanitized_catalog_yaml_sha256']:raise ValueError('Public catalog index checksum changed')
    instance=manifest['instance']
    return {'ir_version':'0.1.0','composition_id':'v2_'+instance['split']+'_'+instance['id'],
        'catalog_snapshot':{'catalog_id':'serviceflow_catalog','version':manifest['catalog']['version'],
                            'sha256':manifest['catalog']['sanitized_catalog_yaml_sha256']},
        'source':{'dataset_id':design['source_dataset_id'],'dataset_version':design['source_dataset_version'],
                  'benchmark_id':instance['benchmark_id'],'split':instance['split'],'pipeline_id':instance['id'],
                  'description_path':'task.md','description_sha256':manifest['task']['description_sha256']}}


def messages(workspace,manifest,design,condition,schema,metadata):
    view=prompts.build_visible_view(workspace,'m3')
    files=[{'path':p.relative_to(workspace).as_posix(),'bytes':p.stat().st_size} for p in sorted((workspace/'fixtures').rglob('*')) if p.is_file()]
    codec=compact_ir.Codec(schema,metadata)
    output_schema=schema if condition=='full_ir_json' else codec.schema
    system=('Compose services from the supplied public task and catalog. Return exactly one minified JSON object, no fences, tools, or explanation. '
            'Use concise prose satisfying schema minimum lengths. Never invent input data or use hidden expected answers. '
            'Represent unresolved requirements explicitly. Your service choices, artifacts, parameters, policies, runtime settings, source-step accounting and wiring remain your decisions.')
    user=('PUBLIC TASK\n'+view['task']+'\nPUBLIC CANDIDATE SETS\n'+view['candidates']+'\nPUBLIC CATALOG\n'+view['catalog']+
        '\nPUBLIC ARTIFACT CONTRACTS\n'+view.get('contracts','(none)')+'\nPUBLIC FIXTURE FILE INDEX\n'+json.dumps(files,separators=(',',':'))+
        '\nPUBLIC FIXTURE PREVIEWS\n'+view.get('fixtures','(none)')+'\nVERIFIED PUBLIC BOOKKEEPING\n'+json.dumps(metadata,separators=(',',':'))+
        '\nREQUIREMENTS\nUse the public candidate sets and source step identifiers. Bind required service ports/parameters, preserve scalar types, '
        'and provide consistent intent inputs/outputs, producers, consumers, and control flow. An unavailable source is not evidence that it can be fabricated. '
        'Declare explicit public fixture links when supported by the visible input. Do not generate executable code.\n')
    if condition=='compact_ir_json':
        user+=('TRANSPORT\nReturn {"format":"'+compact_ir.FORMAT+'","record":...}. Each fixed record is an array in the schema slot order, '
               'including a final optional_fields object only where the schema declares it. Empty arrays/objects are explicit values, not omitted slots. '
               'Arbitrary parameter dictionaries remain dictionaries. The harness restores exactly the four verified bookkeeping fields above; '
               'it supplies no service choices, missing parameters, artifact roles, graph edges, policies, runtime choices, or other semantic values.\n')
    elif condition=='full_ir_json':user+='TRANSPORT\nReturn the full ServiceFlowIR JSON object. Use exactly the verified bookkeeping values above.\n'
    else:raise ValueError('Unknown pilot condition')
    user+='OUTPUT SCHEMA\n'+json.dumps(output_schema,separators=(',',':'))
    return [{'role':'system','content':system},{'role':'user','content':user}]


def prepare(args):
    design=replay.read_json(CONFIG);models=replay.read_json(MODELS)['models']
    model_id=args.model or design['default_model'];case=args.instance or design['default_case']
    if model_id not in models or case not in design['allowed_cases']:raise ValueError('Choose a configured model and a preselected family case')
    model=copy.deepcopy(models[model_id]);transport.validate_model(model)
    if args.max_output_tokens is not None:
        if args.max_output_tokens<1 or args.max_output_tokens>model['max_tokens']:raise ValueError('Output limit must be positive and no larger than the declared pilot budget')
        model['max_tokens']=args.max_output_tokens
    root=ROOT/design['parent_response_audit'];previous=replay.read_json(root/'run.json')
    if previous['status']!='complete' or previous.get('source_inputs_unchanged') is not True:raise ValueError('Completed unchanged response audit required')
    hashes=parent.verify_hashes(root,previous)
    for saved in previous['completed_cells'].values():
        if controls.sha256(Path(saved['path']))!=saved['sha256']:raise ValueError('Prior response checkpoint changed')
    inventory=replay.read_json(ROOT/replay.read_json(parent.CONFIG)['inventory_run']/'run.json')
    workspace=Path(inventory['control_directory'])/'cases'/case/'public_workspace'/case
    context=census.public_context(workspace);manifest=controls.load(workspace/'workspace.yaml')
    verify_prompt_inventory(workspace,manifest)
    metadata=public_metadata(workspace,manifest,design)
    schema=controls.load(workspace/'schemas/serviceflow_ir.schema.json')
    if any(isinstance(v,dict) and any(k in v and not str(v[k]).startswith('#') for k in ('$ref','$dynamicRef')) for v in census.legacy.analysis.walk(schema)):
        raise ValueError('Nonlocal schema resolution is not supported')
    codec=compact_ir.Codec(schema,metadata)
    requests={condition:transport.request(model,messages(workspace,manifest,design,condition,schema,metadata)) for condition in design['conditions']}
    if len(requests)!=design['maximum_inference_requests']:raise ValueError('Pilot request budget changed')
    paths=[*FILES,root/'run.json',root/'input_sha256.json']
    paths.extend(Path(v['path']) for v in previous['completed_cells'].values())
    hashes.update({str(p.resolve()):controls.sha256(p) for p in paths})
    # Parent pins already cover the frozen public workspace and prompt builder.
    return design,model_id,model,case,workspace,context,schema,metadata,codec,requests,hashes


def classify(payload,condition,codec,schema,workspace,context):
    observed=transport.observe(payload)
    record={k:v for k,v in observed.items() if k!='text'}
    record['schema_conformant']=False;record['metadata_conformant']=False
    record['semantic_outcome']='not_measured';record['public_gates']='not_remeasured'
    text=observed.get('text');expanded=None
    if not isinstance(text,str) or not text.strip() or observed['status'] in ('unexpected_tool_call','unsupported_content_shape','content_filtered'):
        return record,expanded
    try:
        value=compact_ir.strict_json(text)
    except (ValueError,TypeError,RecursionError):
        record['format_outcome']='invalid_strict_json'
        if observed['status']=='complete_text':record['status']='syntax_error'
        return record,expanded
    try:
        if condition=='compact_ir_json':expanded=codec.decode(value)
        else:
            compact_ir.Draft202012Validator(schema).validate(value);expanded=value
        record['schema_conformant']=True
    except Exception as exc:
        record.update(format_outcome='schema_or_codec_error',format_error_type=type(exc).__name__)
        if observed['status']=='complete_text':record['status']='schema_error'
        return record,None
    record['metadata_conformant']=all(expanded[k]==codec.metadata[k] for k in compact_ir.BOOKKEEPING)
    if not record['metadata_conformant']:
        record['format_outcome']='public_metadata_mismatch'
        if observed['status']=='complete_text':record['status']='metadata_mismatch'
        return record,expanded
    record['format_outcome']='schema_and_public_metadata_conformant'
    if observed['status']=='complete_text':record['status']='complete_ir'
    elif observed['status']=='output_limit':record['status']='complete_ir_with_length_stop'
    catalog=census.Catalog()
    record['static_diagnostics']=census.analysis.analyze(expanded,schema=schema,
        catalog_get=lambda service,version:catalog.get(workspace,service,version),workspace=workspace,scenarios=context['scenarios'],load=controls.load)
    return record,expanded


def run_cell(attempt,condition,request_args,model,secret,codec,schema,workspace,context,client_factory=None):
    """At most once: never automatically repeat an ambiguously dispatched call."""
    attempt.mkdir(parents=True,exist_ok=True)
    response=attempt/'completion.json';dispatched=attempt/'dispatched.json'
    if not response.is_file():
        if dispatched.is_file():
            return {'status':'interrupted_outcome_unknown','schema_conformant':False,'semantic_outcome':'not_measured','automatic_redispatch':False}
        controls.write_json(attempt/'request.json',transport.sanitize(request_args,secret))
        controls.write_json(dispatched,{'dispatched_at':datetime.now(timezone.utc).isoformat(),'automatic_retries':0,
            'configured_max_tokens':model['max_tokens'],'note':'Written before SDK call; its existence prevents automatic duplicate dispatch'})
        payload=transport.complete(model,request_args,secret,client_factory)
        controls.write_json(response,payload)
    else:payload=replay.read_json(response)
    observed=transport.observe(payload)
    if isinstance(observed.get('text'),str):(attempt/'assistant_content.txt').write_text(observed['text'])
    record,expanded=classify(payload,condition,codec,schema,workspace,context)
    if expanded is not None:
        controls.write_json(attempt/'expanded_ir.json',expanded)
        if record['schema_conformant'] and record.get('metadata_conformant'):
            encoded=codec.encode(expanded);decoded=codec.decode(encoded)
            record['codec_roundtrip_equal']=decoded==expanded
            controls.write_json(attempt/'lossless_compact_equivalent.json',encoded)
            record['serialized_full_characters']=len(json.dumps(expanded,separators=(',',':')))
            record['serialized_compact_characters']=len(json.dumps(encoded,separators=(',',':')))
    record['latency_s']=payload.get('latency_s')
    record['configured_max_tokens']=model['max_tokens']
    record['artifact_directory']=str(attempt)
    controls.write_json(attempt/'result.json',record)
    return record


def render(run):
    lines=['# V2 full/compact generation transport pilot','',f"Package {run['package_version']}; protocol {run['audit_protocol_version']}; state {run['status']}.",
        f"Case {run['case']}; configured model {run['model_id']}; at most {len(run['requests'])} new inference requests.",
        'Exploratory M3-like one-pass generation, not M0–M5 replication or a semantic score. No workflow execution or repair loop.','',
        '| Condition | Outcome | Finish reason | Full IR schema | Public identity | Completion tokens |','|---|---|---|---|---|---:|']
    for condition in run['design']['conditions']:
        r=run['results'].get(condition,{'status':'pending'});usage=r.get('usage') if isinstance(r.get('usage'),dict) else {}
        lines.append(f"| {condition} | {r['status']} | {r.get('finish_reason')} | {r.get('schema_conformant')} | {r.get('metadata_conformant')} | {usage.get('completion_tokens')} |")
    lines+=['','All response fields, including available reasoning/tool fields, are preserved separately from final content. Tool calls are never executed.',
        'A length stop remains visible even if a complete schema-conformant candidate exists. Missing token metadata remain unknown.',
        'Valid schema/identity does not establish contract closure, data correctness, runtime availability, or G6-Assert success.',
        'Full/compact contexts contain equivalent public information but different output schemas/instructions; prompt lengths are recorded.',
        'Original v1 code, outputs, scores, paper, and published deposit remain unchanged.','']
    return '\n'.join(lines)


def output_checkpoint(attempt):
    files={p.relative_to(attempt).as_posix():controls.sha256(p) for p in attempt.rglob('*') if p.is_file()}
    return {'path':str(attempt/'result.json'),'sha256':controls.sha256(attempt/'result.json'),'files':files}


def verify_completed(run):
    for saved in run['result_files'].values():
        root=Path(saved['path']).parent
        actual={p.relative_to(root).as_posix():controls.sha256(p) for p in root.rglob('*') if p.is_file()}
        if actual!=saved['files']:raise ValueError('Completed pilot response/request/result changed')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model');parser.add_argument('--instance');parser.add_argument('--max-output-tokens',type=int)
    parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv)
    print('Verifying frozen evidence and preparing the public full/compact request pair...',flush=True)
    design,model_id,model,case,workspace,context,schema,metadata,codec,requests,hashes=prepare(args)
    plan={'case':case,'model':model_id,'conditions':list(requests),'maximum_new_inference_requests':len(requests),
          'configured_max_output_tokens_per_call':model['max_tokens'],'automatic_retries':0,
          'prompt_characters':{k:sum(len(m['content']) for m in r['messages']) for k,r in requests.items()},
          'semantic_execution':False,'gold_or_private_answers_in_prompts':False}
    if args.dry_run:print(json.dumps(plan,indent=2));return 0
    secret=os.environ.get(model['api_key_env'])
    if not secret:raise ValueError('Set '+model['api_key_env']+' in your terminal; do not pass the token as a CLI argument')
    if args.resume:
        output=args.resume.resolve();run=replay.read_json(output/'run.json')
        if run['input_fingerprint']!=controls.fingerprint(hashes) or run['requests']!=requests or run['model_config']!=model or run['case']!=case:
            raise ValueError('Pilot code/input/config changed; cannot resume')
        verify_completed(run)
    else:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');output=ROOT/'audit/outputs'/f'package_v2_generation_pilot__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True,exist_ok=False)
        run={'package_version':design['package_version'],'audit_protocol_version':design['audit_protocol_version'],'design':design,
            'case':case,'model_id':model_id,'model_config':model,'requests':transport.sanitize(requests,secret),'metadata':metadata,
            'input_fingerprint':controls.fingerprint(hashes),'environment':controls.environment(),'plan':plan,'results':{},'result_files':{}}
        controls.write_json(output/'input_sha256.json',hashes)
        controls.write_json(output/'compact_output.schema.json',codec.schema);controls.write_json(output/'compact_slots.json',codec.columns)
        controls.write_json(output/'full_output.schema.json',schema)
        for path in FILES:
            target=output/'implementation'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    run['status']='running';controls.write_json(output/'run.json',run);print('Output: '+str(output),flush=True)
    tests=subprocess.run([sys.executable,'-m','pytest','-q',str(TESTS)],cwd=ROOT,capture_output=True,text=True,timeout=60)
    (output/'verification.txt').write_text(tests.stdout+tests.stderr)
    if tests.returncode:
        run['status']='verification_failed';controls.write_json(output/'run.json',run);print('verification_failed: '+str(output/'verification.txt'),flush=True);return 1
    for condition in design['conditions']:
        if condition in run['results']:continue
        parent.verify_hashes(output,run)
        # Every attempt has a fixed path so an interrupted dispatch cannot be
        # bypassed by allocating another paid attempt on resume.
        attempt=output/'cells'/condition
        record=run_cell(attempt,condition,requests[condition],model,secret,codec,schema,workspace,context)
        controls.write_json(attempt/'result.json',record)
        run['results'][condition]=record;run['result_files'][condition]=output_checkpoint(attempt)
        controls.write_json(output/'run.json',run);(output/'summary.md').write_text(render(run))
        print(condition+': '+record['status'],flush=True)
    try:parent.verify_hashes(output,run);unchanged=True
    except ValueError as exc:unchanged=False;run['integrity_error']=str(exc)
    run['source_inputs_unchanged']=unchanged
    run['status']='inputs_changed' if not unchanged else 'complete_with_errors' if any(r['status'] in ('inference_error','interrupted_outcome_unknown') for r in run['results'].values()) else 'complete'
    controls.write_json(output/'run.json',run);(output/'summary.md').write_text(render(run))
    print(run['status']+': '+str(output/'summary.md'),flush=True)
    return 0 if run['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
