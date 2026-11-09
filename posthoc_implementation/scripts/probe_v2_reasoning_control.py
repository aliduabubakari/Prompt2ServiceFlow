#!/usr/bin/env python3
"""Two tiny calls to test a documented thinking control without IR generation."""
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
import run_v2_generation_pilot as generation

controls,replay,parent=generation.controls,generation.replay,generation.parent
CONFIG=ROOT/'audit/v2/reasoning_probe.json'
TESTS=ROOT/'tests/unit/test_v2_reasoning_probe.py'
FILES=[Path(__file__).resolve(),CONFIG,TESTS,ROOT/'audit/v2/REASONING_CONTROL_PROBE.md']


def build_requests(design,model):
    settings=copy.deepcopy(model);settings['max_tokens']=design['requested_max_tokens'];settings['temperature']=0.0
    basic=generation.transport.request(settings,[{'role':'user','content':design['prompt']}])
    changed={**copy.deepcopy(basic),'reasoning_effort':'none'}
    return settings,{'server_default':basic,'reasoning_effort_none':changed}


def evaluate(payload,expected,requested):
    observed=generation.transport.observe(payload);text=observed.pop('text',None)
    observed.update(probe_json_matches=False,semantic_outcome='not_measured',requested_max_tokens=requested)
    if isinstance(text,str) and text.strip():
        try:observed['probe_json_matches']=generation.compact_ir.strict_json(text)==expected
        except (ValueError,TypeError,RecursionError):pass
    raw=payload.get('response') or {};choices=raw.get('choices') or []
    message=choices[0].get('message',{}) if len(choices)==1 and isinstance(choices[0],dict) else {}
    observed['reasoning_character_counts']={k:len(message[k]) for k in ('reasoning','reasoning_content','analysis') if isinstance(message.get(k),str)}
    observed['system_fingerprint']=raw.get('system_fingerprint')
    usage=observed.get('usage') if isinstance(observed.get('usage'),dict) else {}
    completion=usage.get('completion_tokens')
    observed['recorded_completion_exceeds_requested_limit']=completion>requested if isinstance(completion,int) else None
    observed['latency_s']=payload.get('latency_s')
    observed['probe_success']=observed['status']=='complete_text' and observed['probe_json_matches']
    return observed


def execute(attempt,request,model,secret,expected,client_factory=None):
    attempt.mkdir(parents=True,exist_ok=True);response=attempt/'completion.json';dispatch=attempt/'dispatched.json'
    if not response.is_file():
        if dispatch.is_file():return {'status':'interrupted_outcome_unknown','probe_json_matches':False,'semantic_outcome':'not_measured'}
        controls.write_json(attempt/'request.json',generation.transport.sanitize(request,secret))
        controls.write_json(dispatch,{'dispatched_at':datetime.now(timezone.utc).isoformat(),'automatic_retries':0})
        payload=generation.transport.complete(model,request,secret,client_factory)
        controls.write_json(response,payload)
    else:payload=replay.read_json(response)
    result=evaluate(payload,expected,model['max_tokens'])
    controls.write_json(attempt/'result.json',result)
    return result


def prepare():
    design=replay.read_json(CONFIG);root=ROOT/design['parent_pilot'];previous=replay.read_json(root/'run.json')
    if previous['status']!='complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged generation pilot required')
    hashes=parent.verify_hashes(root,previous);generation.verify_completed(previous)
    model=copy.deepcopy(replay.read_json(generation.MODELS)['models'][design['model_id']])
    generation.transport.validate_model(model)
    settings,requests=build_requests(design,model)
    if list(requests)!=design['conditions'] or len(requests)!=design['maximum_inference_requests']:raise ValueError('Probe design changed')
    paths=[*FILES,generation.MODELS,root/'run.json',root/'input_sha256.json']
    for saved in previous['result_files'].values():paths.extend(Path(saved['path']).parent/name for name in saved['files'])
    hashes.update({str(path.resolve()):controls.sha256(path) for path in paths})
    return design,settings,requests,hashes


def render(run):
    lines=['# SINTEF reasoning-control compatibility probe','',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; model {run['design']['model_id']}.",
        'Two small inference requests maximum; no benchmark/semantic score or v1 changes.','',
        '| Condition | Outcome | Finish | Exact probe JSON | Final characters | Reasoning characters | Completion tokens |',
        '|---|---|---|---|---:|---:|---:|']
    for condition in run['design']['conditions']:
        row=run['results'].get(condition,{'status':'pending'});usage=row.get('usage') if isinstance(row.get('usage'),dict) else {}
        lines.append(f"| {condition} | {row['status']} | {row.get('finish_reason')} | {row.get('probe_json_matches')} | {row.get('visible_content_characters')} | {sum(row.get('reasoning_character_counts',{}).values())} | {usage.get('completion_tokens')} |")
    lines+=['','`reasoning_effort:none` support/effect is not inferred merely from HTTP acceptance or a fingerprint.',
        'A short successful response does not prove the maximum effective output capacity or success on the large IR task.',
        'Record any thinking-mode change as a new model configuration and apply it consistently in later method comparisons.','']
    return '\n'.join(lines)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv)
    print('Verifying the completed generation pilot and preparing the serving-control probe...',flush=True)
    design,model,requests,hashes=prepare()
    if args.dry_run:
        print(json.dumps({'model':design['model_id'],'conditions':list(requests),'maximum_new_requests':len(requests),
            'requested_output_limit_per_call':model['max_tokens'],'automatic_retries':0,'semantic_scores':False},indent=2));return 0
    secret=os.environ.get(model['api_key_env'])
    if not secret:raise ValueError('Set '+model['api_key_env']+' in the terminal')
    if args.resume:
        output=args.resume.resolve();run=replay.read_json(output/'run.json')
        if run['input_fingerprint']!=controls.fingerprint(hashes) or run['requests']!=requests:raise ValueError('Probe inputs/code changed')
        generation.verify_completed(run)
    else:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');output=ROOT/'audit/outputs'/f'package_v2_reasoning_probe__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True,exist_ok=False)
        run={'package_version':design['package_version'],'audit_protocol_version':design['audit_protocol_version'],'design':design,'model_config':model,
            'requests':requests,'input_fingerprint':controls.fingerprint(hashes),'environment':controls.environment(),'results':{},'result_files':{}}
        controls.write_json(output/'input_sha256.json',hashes)
        for path in FILES:
            target=output/'implementation'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    run['status']='running';controls.write_json(output/'run.json',run);print('Output: '+str(output),flush=True)
    tests=subprocess.run([sys.executable,'-m','pytest','-q',str(TESTS)],cwd=ROOT,capture_output=True,text=True,timeout=60)
    (output/'verification.txt').write_text(tests.stdout+tests.stderr)
    if tests.returncode:
        run['status']='verification_failed';controls.write_json(output/'run.json',run);print('verification_failed: '+str(output/'verification.txt'),flush=True);return 1
    for condition,request in requests.items():
        if condition in run['results']:continue
        parent.verify_hashes(output,run)
        attempt=output/'cells'/condition
        result=execute(attempt,request,model,secret,design['expected'])
        controls.write_json(attempt/'result.json',result)
        run['results'][condition]=result;run['result_files'][condition]=generation.output_checkpoint(attempt)
        controls.write_json(output/'run.json',run);print(condition+': '+result['status'],flush=True)
    try:parent.verify_hashes(output,run);unchanged=True
    except ValueError as exc:unchanged=False;run['integrity_error']=str(exc)
    run['source_inputs_unchanged']=unchanged
    run['status']='inputs_changed' if not unchanged else 'complete_with_errors' if any(r['status'] in ('inference_error','interrupted_outcome_unknown') for r in run['results'].values()) else 'complete'
    controls.write_json(output/'run.json',run);(output/'summary.md').write_text(render(run))
    print(run['status']+': '+str(output/'summary.md'),flush=True)
    return 0 if run['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
