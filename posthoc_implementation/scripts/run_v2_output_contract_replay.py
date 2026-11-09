#!/usr/bin/env python3
"""Replay saved IR after a public-output mock compiler correction; zero LLM calls."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src'),str(ROOT/'audit/v2'),str(ROOT/'audit')]
import replay_v2_corpus_assertions_v2 as baseline
import public_output_runtime as compiler
import output_contract_evaluator as evaluator

CONFIG=ROOT/'audit/v2/output_contract_replay.v1.json'
TEST=ROOT/'tests/unit/test_v2_output_contract_replay.py'
DOC=ROOT/'audit/v2/OUTPUT_CONTRACT_REPLAY.md'
IMPLEMENTATION=[Path(__file__).resolve(),Path(compiler.__file__),Path(evaluator.__file__),CONFIG,TEST,DOC]
read,write=baseline.read,baseline.engine.write


def prepare():
    design=read(CONFIG);lock=ROOT/design['freeze_lock']
    baseline.previous.previous.previous.verify_named_inputs(ROOT,read(lock)['files'],[p.relative_to(ROOT).as_posix() for p in IMPLEMENTATION])
    if design['llm_requests_permitted']!=0 or read(lock)['protocol_version']!=design['protocol_version']:raise ValueError('Invalid frozen design')
    p=baseline.prepare();parent=ROOT/design['baseline_run'];old=read(parent/'run.json');seal=read(parent/'output_sha256.json')
    if old['status']!='complete' or not old.get('source_inputs_unchanged') or not old['control_gate']['pass']:raise ValueError('Completed baseline required')
    if old['design']!=p['design'] or old['input_fingerprint']!=baseline.controls.fingerprint(p['hashes']):raise ValueError('Baseline design/input mismatch')
    if read(parent/'plan.json')!=p['plan'] or read(parent/'input_sha256.json')!=p['hashes']:raise ValueError('Baseline roster/input pins differ')
    baseline.previous.previous.previous.verify_seal(parent,seal)
    if seal['output_fingerprint']!=design['baseline_output_fingerprint']:raise ValueError('Frozen baseline output mismatch')
    if set(old['completed_cells'])!={r['source']['id'] for r in p['plan']}:raise ValueError('Baseline incomplete')
    hashes=dict(p['hashes']);publics={};plan=[]
    for index,original in enumerate(p['plan']):
        row=copy.deepcopy(original);source=row['source'];key=source['id']
        prior=baseline.verify_checkpoint(old['completed_cells'][key],source,parent)
        row['baseline_role_pass']=prior.get('role_matched_assertion_pass') is True
        if row['admission']=='eligible_frozen_mock':
            case=source['case']
            if case not in publics:
                workspace=ROOT/design['public_controls_root']/'cases'/case/'public_workspace'/case
                publics[case]=compiler.PublicWorkspace(workspace)
            row['compilation']=compiler.compile_plan(Path(row['submission']),publics[case])
            for path,digest in row['compilation']['public_inputs'].items():
                if path in hashes and hashes[path]!=digest:raise ValueError('Public source pin changed')
                hashes[path]=digest
        plan.append(row)
        if (index+1)%330==0:print(f"preflight: planned {index+1}/{len(p['plan'])} original identities",flush=True)
    for path in [*IMPLEMENTATION,lock,parent/'output_sha256.json',*[parent/name for name in seal['files']]]:
        key=str(path.resolve());digest=baseline.controls.sha256(path)
        if key in hashes and hashes[key]!=digest:raise ValueError('Pinned implementation/evidence changed')
        hashes[key]=digest
    return {'design':design,'hashes':hashes,'plan':plan,'directory_inventories':p['directory_inventories']}


def authored_control(root):
    """One public false-valued contract, plus a contradictory private check."""
    root=Path(root);public=root/'public';source=root/'source';reference=root/'reviewed'
    schema={'type':'object','required':['accepted','count'],'properties':{'accepted':{'const':False},'count':{'type':'integer','minimum':7}}}
    descriptor={'service_id':'synthetic','version':'1','interface':{'outputs':[{'name':'result','media_type':'application/json'}]},
        'contracts':[{'contract_id':'output','type':'json_schema','applies_to':'output','target':'result','expression':json.dumps(schema)}]}
    write(public/'catalog/catalog.yaml',{'services':[{'service_id':'synthetic','version':'1','descriptor_path':'services/synthetic.yaml'}]})
    write(public/'catalog/services/synthetic.yaml',descriptor)
    entries=[{'path':p.relative_to(public).as_posix(),'sha256':compiler.metadata.sha(p)} for p in public.rglob('*') if p.is_file()]
    write(public/'workspace.yaml',{'files':entries,'catalog':{'version':'test','pinned_catalog_yaml_sha256':'pin'}})
    ir={'catalog_snapshot':{'version':'test','sha256':'pin'},'artifacts':[{'artifact_id':'model_output','media_type':'application/json','data_type':'object'}],
        'bindings':[{'intent_id':'test_intent','service_id':'synthetic','service_version':'1','output_bindings':[{'port':'result','artifact_id':'model_output'}],'parameter_bindings':{'keep':'unchanged'}}]}
    write(source/'serviceflow.yaml',ir)
    runtime={'tasks':[{'intent_id':'test_intent','script':'scripts/run.py','arguments':['--workspace','{workspace}','--fixtures','{fixtures}']}],
        'scenarios':[{'name':'test','parameters':{},'fixture_root':'fixtures/inputs'}]}
    write(source/'runtime/manifest.yaml',runtime);(source/'runtime/scripts').mkdir()
    (source/'runtime/scripts/run.py').write_text(compiler.original._script_text([{'artifact_id':'model_output','data_type':'object','media_type':'application/json'}]))
    plan=compiler.compile_plan(source,compiler.PublicWorkspace(public))
    compiler.materialize(plan,source,root/'compiled')
    write(reference/'runtime/manifest.yaml',runtime);(reference/'fixtures/inputs').mkdir(parents=True)
    definition={'assertion_id':'accepted','type':'json_path_equals','path':'artifacts/reviewed_output.json','json_path':'accepted','expected':False}
    write(reference/'gold/assertions.yaml',{'scenarios':[{'scenario':'test','assertions':[definition]}]})
    write(reference/'gold/serviceflow.yaml',ir)
    write(reference/'gold/artifact_mappings.yaml',{'mappings':[{'intent_id':'test_intent','outputs':{'result':'reviewed_output'}}]})
    result=evaluator.replay(root/'compiled',reference,root/'execution','authored',writer_plan=plan['writers'])
    snapshot=root/'execution/scenarios/test/snapshot'
    wrong={**definition,'path':'artifacts/model_output.json','expected':True}
    rejected=not evaluator.score(snapshot,{'scenario':'test','_errors':[]},[wrong])['reviewed_assertion_pass']
    write(reference/'gold/assertions.yaml',{'scenarios':[{'scenario':'test','assertions':[wrong]}]})
    after=compiler.compile_plan(source,compiler.PublicWorkspace(public))
    checks={'public_false_contract_pass':result['role_matched_assertion_pass'],'contradictory_expected_value_rejected':rejected,
        'private_expected_value_cannot_change_compilation':after==plan,'saved_ir_unchanged':compiler.metadata.sha(root/'compiled/serviceflow.yaml')==compiler.metadata.sha(source/'serviceflow.yaml')}
    checks['pass']=all(checks.values());write(root/'result.json',checks);return checks


def report(output,run,plan):
    results={row['source']['id']:baseline.verify_checkpoint(run['completed_cells'][row['source']['id']],row['source'],output)
        for row in plan if row['source']['id'] in run['completed_cells']}
    table=[]
    for row in plan:
        source=row['source'];result=results.get(source['id'],{});compilation=row.get('compilation',{})
        table.append({**{k:source[k] for k in ['id','model','method','case','split','sample_index']},
            'admission':row['admission'],'state':result.get('state','pending'),'original_pass':source['published_semantic_success'],
            'baseline_role_pass':row['baseline_role_pass'],'corrected_role_pass':result.get('role_matched_assertion_pass'),
            'changed_scripts':compilation.get('changed_scripts',0),'compiler_version':compiler.VERSION})
    with (output/'paired_run_level.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    aggregate={'declared':len(plan),'completed':len(results),'pending':len(plan)-len(results),
        'baseline_role_passes':sum(row['baseline_role_pass'] for row in plan),'corrected_role_passes':sum(r.get('role_matched_assertion_pass') is True for r in results.values()),
        'changed_scripts':sum(r.get('compilation',{}).get('changed_scripts',0) for r in plan),
        'compiler_output_states':dict(Counter(o['state'] for r in plan for o in r.get('compilation',{}).get('outputs',[]))),
        'states':dict(Counter(r['state'] for r in results.values())),'llm_calls':0}
    write(output/'aggregate.json',aggregate)
    lines=['# Public output-contract runtime replay','','Status: '+run['status'],'',run['design']['scope'],'','```json',json.dumps(aggregate,indent=2),'```','',
        '| Model | Method | Declared | Completed | Baseline passes | Corrected runtime passes |','|---|---|---:|---:|---:|---:|']
    for model,method in sorted({(r['model'],r['method']) for r in table}):
        rows=[r for r in table if r['model']==model and r['method']==method]
        lines.append(f"| {model} | {method} | {len(rows)} | {sum(r['state']!='pending' for r in rows)} | {sum(r['baseline_role_pass'] for r in rows)} | {sum(r['corrected_role_pass'] is True for r in rows)} |")
    lines+=['','This is a compiler intervention on saved IR, not a new LLM experiment or an evaluator-only rescore. Public schema examples remain mock outputs. All original identities remain in the denominator; unsupported corrections preserve their original output specification. All held-out expected values and output-role matching rules are unchanged.','']
    (output/'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv);print('Verifying baseline and planning public-contract output corrections; zero LLM calls...',flush=True)
    p=prepare();plan=p['plan'];fingerprint=baseline.previous.suite.adapter.digest(plan)
    if args.dry_run:
        print(json.dumps({'declared':len(plan),'eligible':sum(r['admission']=='eligible_frozen_mock' for r in plan),
            'changed_scripts':sum(r.get('compilation',{}).get('changed_scripts',0) for r in plan),
            'compiler_output_states':dict(Counter(o['state'] for r in plan for o in r.get('compilation',{}).get('outputs',[]))),
            'verified_input_pins':len(p['hashes']),'llm_calls':0,'runtime_executions':0},indent=2));return 0
    if args.resume:
        output=args.resume.resolve()
        if not output.is_relative_to((ROOT/'audit/evaluator_only').resolve()):raise ValueError('Resume outside evaluator-only output root')
        run=read(output/'run.json')
        if run['design']!=p['design'] or run['plan_fingerprint']!=fingerprint or read(output/'input_sha256.json')!=p['hashes'] or read(output/'plan.json')!=plan:raise ValueError('Immutable resume inputs differ')
        if (output/'output_sha256.json').exists():baseline.previous.previous.previous.verify_seal(output,read(output/'output_sha256.json'))
        if not set(run['completed_cells'])<={r['source']['id'] for r in plan}:raise ValueError('Foreign completed cell')
        for row in plan:
            if row['source']['id'] in run['completed_cells']:baseline.verify_checkpoint(run['completed_cells'][row['source']['id']],row['source'],output)
    else:
        output=ROOT/'audit/evaluator_only'/('package_v2_output_contracts__'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'__'+uuid.uuid4().hex[:8]);output.mkdir(parents=True)
        run={'status':'prepared','design':p['design'],'plan_fingerprint':fingerprint,'input_fingerprint':baseline.controls.fingerprint(p['hashes']),'completed_cells':{},'llm_calls':0}
        write(output/'plan.json',plan);write(output/'input_sha256.json',p['hashes']);write(output/'run.json',run)
    print('Output: '+str(output),flush=True)
    try:
        tests=subprocess.run([sys.executable,'-m','pytest','-q',str(TEST)],cwd=ROOT,capture_output=True,text=True,timeout=120)
        (output/('verification_'+uuid.uuid4().hex[:8]+'.txt')).write_text(tests.stdout+tests.stderr)
        if tests.returncode:raise ValueError('Compiler/evaluator verification failed')
        gate=authored_control(output/('controls_'+uuid.uuid4().hex[:8]));run['control_gate']=gate
        if not gate['pass']:raise ValueError('Public output control failed; no source corpus executions')
        run['status']='running'
        for row in plan:
            source=row['source'];name=source['id']
            if name in run['completed_cells']:continue
            directory=output/'cells'/name/('attempt_'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True)
            if row['admission']!='eligible_frozen_mock':result={'state':row['admission'],'role_matched_assertion_pass':None}
            else:
                compiler.materialize(row['compilation'],Path(row['submission']),directory/'compiled_submission')
                write(directory/'compilation.json',row['compilation'])
                result=evaluator.replay(directory/'compiled_submission',Path(row['instance']),directory/'evaluation',name,
                    writer_plan=row['compilation']['writers'],timeout=p['design']['task_timeout_s'])
            result['baseline_role_pass']=row['baseline_role_pass'];result['compiler_version']=compiler.VERSION
            run['completed_cells'][name]=baseline.checkpoint(directory,source,result);write(output/'run.json',run)
            print(f"{len(run['completed_cells'])}/{len(plan)} {name}: {result['state']}",flush=True)
        baseline.verify_inputs(output,run);baseline.previous.previous.verify_directories(p['directory_inventories'])
        run['source_inputs_unchanged']=True;run['status']='complete'
    except BaseException as exc:
        run['status']='interrupted_or_error';run['error']=type(exc).__name__+': '+str(exc)[:1500]
        write(output/'run.json',run);report(output,run,plan);baseline.previous.previous.seal_output(output);raise
    write(output/'run.json',run);report(output,run,plan);baseline.previous.previous.seal_output(output)
    print('complete: '+str(output/'summary.md'),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
