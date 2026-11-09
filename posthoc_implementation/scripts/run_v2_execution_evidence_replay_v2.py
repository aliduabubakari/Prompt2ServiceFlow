#!/usr/bin/env python3
"""Reference controls then saved-IR replay with public file-backed evidence."""
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
import run_v2_output_contract_replay as previous
import execution_evidence_runtime_v2 as compiler
import execution_evidence_evaluator_v2 as evaluator

base=previous.baseline
read,write=previous.read,previous.write
CONFIG=ROOT/'audit/v2/execution_evidence_replay.v2.json'
PROFILE=ROOT/'audit/v2/execution_evidence_profile.v1.json'
TEST=ROOT/'tests/unit/test_v2_execution_evidence_v2.py'
DOC=ROOT/'audit/v2/EXECUTION_EVIDENCE_REPLAY_V2.md'
IMPLEMENTATION=[Path(__file__).resolve(),Path(compiler.__file__),Path(compiler.kernel.__file__),Path(evaluator.__file__),CONFIG,PROFILE,TEST,DOC]


def prepare():
    design=read(CONFIG);lock=ROOT/design['freeze_lock'];profile=read(PROFILE)
    base.previous.previous.previous.verify_named_inputs(ROOT,read(lock)['files'],[p.relative_to(ROOT).as_posix() for p in IMPLEMENTATION])
    if read(lock)['protocol_version']!=design['protocol_version'] or design['llm_requests_permitted']!=0:raise ValueError('Frozen profile/version mismatch')
    parent=ROOT/design['baseline_run'];old=read(parent/'run.json');seal=read(parent/'output_sha256.json')
    parent_design=read(previous.CONFIG);parent_lock=ROOT/parent_design['freeze_lock']
    base.previous.previous.previous.verify_named_inputs(ROOT,read(parent_lock)['files'],[x.relative_to(ROOT).as_posix() for x in previous.IMPLEMENTATION])
    if old['status']!='complete' or not old.get('source_inputs_unchanged') or not old['control_gate']['pass']:raise ValueError('Completed compiler baseline required')
    if old['design']!=parent_design:raise ValueError('Baseline frozen design differs')
    parent_hashes=base.verify_inputs(parent,old);parent_plan=read(parent/'plan.json')
    if base.previous.suite.adapter.digest(parent_plan)!=old['plan_fingerprint'] or len(parent_plan)!=2970 or len({r['source']['id'] for r in parent_plan})!=2970:raise ValueError('Baseline plan/roster differs')
    inventories={}
    for instance in {r['instance'] for r in parent_plan}:
        root=Path(instance)/'fixtures';tree=compiler.previous.metadata.tree(root)
        for relative,digest in tree['files'].items():
            if parent_hashes.get(str((root/relative).resolve()))!=digest:raise ValueError('New/changed reviewed fixture input')
        inventories[str(root)]=tree
    p={'design':parent_design,'hashes':parent_hashes,'plan':parent_plan,'directory_inventories':inventories}
    base.previous.previous.previous.verify_seal(parent,seal)
    if seal['output_fingerprint']!=design['baseline_output_fingerprint']:raise ValueError('Baseline output fingerprint differs')
    hashes=dict(p['hashes']);publics={};plan=[];targets=0;planned_json=0
    cases=sorted({row['source']['case'] for row in p['plan']})
    def public_for(case):
        if case not in publics:publics[case]=compiler.previous.PublicWorkspace(ROOT/p['design']['public_controls_root']/'cases'/case/'public_workspace'/case)
        return publics[case]
    for original in p['plan']:
        row=copy.deepcopy(original);source=row['source'];prior=base.verify_checkpoint(old['completed_cells'][source['id']],source,parent)
        row['baseline_role_pass']=prior.get('role_matched_assertion_pass') is True
        if row['admission']=='eligible_frozen_mock':
            row['compilation']=compiler.extend(row['compilation'],Path(row['submission']),public_for(source['case']),Path(row['instance']),profile)
            # Diagnostic only: these outcomes never enter profile compilation.
            for scenario in prior['scenarios']:
                for check in scenario['role_matched_assertions']:
                    if not check['message'].startswith('output_format_error:'):continue
                    targets+=1;roles=check['path_association'].get('associations',[])
                    paths={w['path'] for role in roles for w in row['compilation']['writers'] if w['intent_id']==role['model_intent'] and w['artifact_id']==role['model_artifact']}
                    planned_json+=len(paths)==1 and next(iter(paths)).endswith('.json')
        plan.append(row)
    controls_root=ROOT/p['design']['public_controls_root'];control_run=read(controls_root/'run.json');references=[]
    for case in cases:
        record=control_run['results'][case]['c2_reference_ir_compiled'];submission=Path(record['artifact_directory'])/'submission'
        public=public_for(case);original=compiler.previous.compile_plan(submission,public)
        compiled=compiler.extend(original,submission,public,ROOT/'benchmark/instances'/case,profile)
        source={'id':'reference/'+case,'case':case,'kind':'staged_reference_compiler_control'}
        references.append({'source':source,'submission':str(submission),'instance':str(ROOT/'benchmark/instances'/case),'compilation':compiled})
    for row in [*plan,*references]:
        if 'compilation' not in row:continue
        compiled=row['compilation']
        additions={**compiled['public_inputs']}
        root=Path(compiled['public_fixture_root'])
        additions.update({str(compiler.previous.metadata.bounded.safe(root,n)):d for n,d in compiled['public_fixture_inventory'].items()})
        source=Path(row['submission']);additions[str(source/'serviceflow.yaml')]=compiled['source_ir_sha256'];additions[str(source/'runtime/manifest.yaml')]=compiled['source_runtime_sha256']
        additions.update({str(compiler.previous.trace.local(source/'runtime',s['path'])):s['source_sha256'] for s in compiled['scripts']})
        for path,digest in additions.items():
            if path in hashes and hashes[path]!=digest:raise ValueError('Pinned public/reference input changed: '+path)
            hashes[path]=digest
    for path in [*IMPLEMENTATION,lock,controls_root/'run.json',parent/'output_sha256.json',*[parent/n for n in seal['files']]]:
        key=str(path.resolve());digest=base.controls.sha256(path)
        if key in hashes and hashes[key]!=digest:raise ValueError('Pinned implementation/source changed')
        hashes[key]=digest
    return {'design':design,'profile':profile,'plan':plan,'references':references,'hashes':hashes,
        'directory_inventories':p['directory_inventories'],'target_format_checks':targets,'planned_json_checks':planned_json}


def execute(row,directory,profile):
    directory.mkdir(parents=True);compiled=row['compilation']
    if compiled.get('profile_blocked'):
        write(directory/'compilation.json',compiled)
        return {'state':'blocked_execution_profile','role_matched_assertion_pass':False,'profile_conformance':{'pass':False,'checked':0,'reason':compiled['profile_blocked']},'compiler_version':compiler.VERSION}
    compiler.previous.materialize(compiled,Path(row['submission']),directory/'compiled_submission')
    write(directory/'compilation.json',compiled)
    result=evaluator.replay(directory/'compiled_submission',Path(row['instance']),directory/'evaluation',row['source']['id'],
        writer_plan=compiled['writers'],public_fixture_root=compiled['public_fixture_root'],public_fixture_inventory=compiled['public_fixture_inventory'],timeout=30)
    conformance=compiler.conformance(directory/'evaluation',compiled,result,profile);write(directory/'profile_conformance.json',conformance)
    result['profile_conformance']=conformance
    result['unrestricted_role_assertion_pass']=result['role_matched_assertion_pass']
    if not conformance['pass']:result['role_matched_assertion_pass']=False
    result['compiler_version']=compiler.VERSION
    return result


def authored_case(root,mode='positive'):
    root=Path(root);public=root/'public';instance=root/'reviewed';source=root/'source'
    for service in ['source_observer','dependent_observer']:
        descriptor={'service_id':service,'version':'1','interface':{'outputs':[{'name':'status','data_type':'status','media_type':'application/json'}]},'contracts':[], 'invocation':{'mock_supported':True}}
        write(public/f'catalog/services/{service}.yaml',descriptor)
    write(public/'catalog/catalog.yaml',{'services':[{'service_id':s,'version':'1','descriptor_path':f'services/{s}.yaml'} for s in ['source_observer','dependent_observer']]})
    fixture=root/'data.csv';fixture.write_text('value\n1\n2\n')
    if mode=='corrupt':fixture=root/'data.json';fixture.write_text('{invalid')
    if mode!='empty':
        for destination in [public/'fixtures/inputs'/fixture.name,instance/'fixtures/inputs'/fixture.name]:
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(fixture.read_bytes())
    (public/'fixtures/inputs').mkdir(parents=True,exist_ok=True);(instance/'fixtures/inputs').mkdir(parents=True,exist_ok=True)
    # An excluded private file must never enter the runtime's visible view.
    write(instance/'fixtures/inputs/private_expected.json',{'expected':999999})
    entries=[{'path':p.relative_to(public).as_posix(),'sha256':compiler.previous.metadata.sha(p)} for p in sorted(public.rglob('*')) if p.is_file()]
    write(public/'workspace.yaml',{'files':entries,'catalog':{'version':'test','pinned_catalog_yaml_sha256':'pin'}})
    artifacts=[{'artifact_id':n+'_status','kind':'artifact','data_type':'status','media_type':'application/json','producer':n,'role':'status'} for n in ['source','final']]
    bindings=[{'intent_id':n,'service_id':s,'service_version':'1','input_bindings':[] if n=='source' else [{'port':'parent','artifact_id':'source_status'}],
        'output_bindings':[{'port':'status','artifact_id':n+'_status'}],'parameter_bindings':{'preserve':'unchanged'}} for n,s in [('source','source_observer'),('final','dependent_observer')]]
    ir={'catalog_snapshot':{'version':'test','sha256':'pin'},'artifacts':artifacts,'bindings':bindings}
    write(source/'serviceflow.yaml',ir)
    tasks=[]
    for intent in ['final','source']:
        script=f'scripts/{intent}.py';tasks.append({'intent_id':intent,'script':script,'dependencies':['source'] if intent=='final' else [],'arguments':['--workspace','{workspace}','--fixtures','{fixtures}']})
        path=source/'runtime'/script;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(compiler.previous.original._script_text([{'artifact_id':intent+'_status','data_type':'status','media_type':'application/json'}]))
    if mode=='broken_upstream':tasks=[{**tasks[0],'dependencies':[]}]
    runtime={'tasks':tasks,'scenarios':[{'name':'test','parameters':{},'fixture_root':'fixtures/inputs'}]}
    write(source/'runtime/manifest.yaml',runtime);write(instance/'runtime/manifest.yaml',runtime)
    assertions=[{'assertion_id':'success','type':'json_path_equals','path':'artifacts/final_status.json','json_path':'success','expected':True},
        {'assertion_id':'rows','type':'json_path_equals','path':'artifacts/source_status.json','json_path':'fixture.record_count','expected':2},
        {'assertion_id':'upstream','type':'json_path_gte','path':'artifacts/final_status.json','json_path':'upstream_artifact_count','minimum':1}]
    write(instance/'gold/assertions.yaml',{'scenarios':[{'scenario':'test','assertions':assertions}]});write(instance/'gold/serviceflow.yaml',ir)
    write(instance/'gold/artifact_mappings.yaml',{'mappings':[{'intent_id':n,'outputs':{'status':n+'_status'}} for n in ['source','final']]})
    public_source=compiler.previous.PublicWorkspace(public);base_plan=compiler.previous.compile_plan(source,public_source)
    plan=compiler.extend(base_plan,source,public_source,instance,read(PROFILE))
    row={'source':{'id':'authored/'+mode},'submission':str(source),'instance':str(instance),'compilation':plan}
    return row,execute(row,root/'result',read(PROFILE))


def report(output,run,plan):
    previous.report(output,run,plan)
    # The inherited table uses its own compiler identifier; label this condition.
    path=output/'paired_run_level.csv'
    with path.open() as handle:rows=list(csv.DictReader(handle))
    for row in rows:row['compiler_version']=compiler.VERSION
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    extra={'reference_controls_completed':len(run['reference_controls']),
        'profile_output_states':dict(Counter(o['profile_state'] for row in plan for o in row.get('compilation',{}).get('outputs',[]))),
        'reference_gate':run.get('reference_gate'),'previous_format_checks':run['target_format_checks'],'planned_json_representation_checks':run['planned_json_checks']}
    aggregate=read(output/'aggregate.json');aggregate.update(extra);write(output/'aggregate.json',aggregate)
    summary=(output/'summary.md').read_text().replace('Public schema examples remain mock outputs.','This condition combines public mock examples with actual file-backed execution evidence.').replace('# Public output-contract runtime replay','# File-backed execution-evidence replay')
    summary+='\n## Profile and reference controls\n\n```json\n'+json.dumps(extra,indent=2)+'\n```\n'
    (output/'summary.md').write_text(summary)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path);args=parser.parse_args(argv)
    print('Verifying public inputs, staged references and the execution-evidence profile; no LLM calls...',flush=True)
    p=prepare();fingerprint=base.previous.suite.adapter.digest({'models':p['plan'],'references':p['references']})
    if args.dry_run:
        print(json.dumps({'declared':len(p['plan']),'eligible':sum(r['admission']=='eligible_frozen_mock' for r in p['plan']),
            'blocked_execution_profiles':sum(bool(r.get('compilation',{}).get('profile_blocked')) for r in p['plan']),
            'reference_controls':len(p['references']),'profile_states':dict(Counter(o['profile_state'] for r in p['plan'] for o in r.get('compilation',{}).get('outputs',[]))),
            'previous_format_checks':p['target_format_checks'],'planned_json_checks':p['planned_json_checks'],'verified_input_pins':len(p['hashes']),'llm_calls':0,'runtime_executions':0},indent=2));return 0
    if args.resume:
        output=args.resume.resolve()
        if not output.is_relative_to((ROOT/'audit/evaluator_only').resolve()):raise ValueError('Resume outside evaluator-only root')
        run=read(output/'run.json')
        if (run['design']!=p['design'] or run['plan_fingerprint']!=fingerprint or run['input_fingerprint']!=base.controls.fingerprint(p['hashes'])
            or read(output/'input_sha256.json')!=p['hashes'] or read(output/'plan.json')!=p['plan'] or read(output/'reference_plan.json')!=p['references']):raise ValueError('Immutable resume design/input mismatch')
        if not set(run['completed_cells'])<={r['source']['id'] for r in p['plan']} or not set(run['reference_controls'])<={r['source']['id'] for r in p['references']}:raise ValueError('Foreign completed model/reference identity')
        if (output/'output_sha256.json').exists():base.previous.previous.previous.verify_seal(output,read(output/'output_sha256.json'))
    else:
        output=ROOT/'audit/evaluator_only'/('package_v2_execution_evidence__'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'__'+uuid.uuid4().hex[:8]);output.mkdir(parents=True)
        run={'status':'prepared','design':p['design'],'input_fingerprint':base.controls.fingerprint(p['hashes']),'plan_fingerprint':fingerprint,
            'completed_cells':{},'reference_controls':{},'target_format_checks':p['target_format_checks'],'planned_json_checks':p['planned_json_checks'],'llm_calls':0}
        write(output/'input_sha256.json',p['hashes']);write(output/'plan.json',p['plan']);write(output/'reference_plan.json',p['references']);write(output/'run.json',run)
    print('Output: '+str(output),flush=True)
    try:
        tests=subprocess.run([sys.executable,'-m','pytest','-q',str(TEST)],cwd=ROOT,capture_output=True,text=True,timeout=120)
        (output/('verification_'+uuid.uuid4().hex[:8]+'.txt')).write_text(tests.stdout+tests.stderr)
        if tests.returncode:raise ValueError('Positive/negative profile controls failed; no reference/model replays')
        reference_results=[]
        for row in p['references']:
            name=row['source']['id']
            if name in run['reference_controls']:result=base.verify_checkpoint(run['reference_controls'][name],row['source'],output)
            else:
                directory=output/'cells'/name/('attempt_'+uuid.uuid4().hex[:8]);result=execute(row,directory,p['profile'])
                run['reference_controls'][name]=base.checkpoint(directory,row['source'],result);write(output/'run.json',run)
            reference_results.append(result)
            print(f"reference {len(reference_results)}/110 {row['source']['case']}: conformance={result['profile_conformance']['pass']}, assertions={result['role_matched_assertion_pass']}",flush=True)
        gate={'pass':len(reference_results)==110 and all(r['profile_conformance']['pass'] for r in reference_results) and sum(r['profile_conformance']['checked'] for r in reference_results)>0,
            'profile_outputs_checked':sum(r['profile_conformance']['checked'] for r in reference_results),
            'reference_full_assertion_passes':sum(r['role_matched_assertion_pass'] for r in reference_results),
            'scope':'Profile/schema and evidence conformance gate; full held-out reference outcomes are reported separately and never select cases.'}
        run['reference_gate']=gate;write(output/'run.json',run)
        if not gate['pass']:raise ValueError('Reference profile conformance failed; no model corpus executions')
        run['status']='running'
        for row in p['plan']:
            source=row['source'];name=source['id']
            if name in run['completed_cells']:base.verify_checkpoint(run['completed_cells'][name],source,output);continue
            directory=output/'cells'/name/('attempt_'+uuid.uuid4().hex[:8])
            if row['admission']=='eligible_frozen_mock':result=execute(row,directory,p['profile'])
            else:directory.mkdir(parents=True);result={'state':row['admission'],'role_matched_assertion_pass':None}
            result['baseline_role_pass']=row['baseline_role_pass'];result['compiler_version']=compiler.VERSION
            run['completed_cells'][name]=base.checkpoint(directory,source,result);write(output/'run.json',run)
            print(f"{len(run['completed_cells'])}/{len(p['plan'])} {name}: {result['state']}",flush=True)
        base.verify_inputs(output,run);base.previous.previous.verify_directories(p['directory_inventories'])
        run['source_inputs_unchanged']=True;run['status']='complete'
    except BaseException as exc:
        run['status']='interrupted_or_error';run['error']=type(exc).__name__+': '+str(exc)[:1500]
        write(output/'run.json',run);report(output,run,p['plan']);base.previous.previous.seal_output(output);raise
    write(output/'run.json',run);report(output,run,p['plan']);base.previous.previous.seal_output(output)
    print('complete: '+str(output/'summary.md'),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
