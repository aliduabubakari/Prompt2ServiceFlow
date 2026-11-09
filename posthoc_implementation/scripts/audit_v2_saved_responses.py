#!/usr/bin/env python3
"""Offline diagnosis of every parse-error cell with missing final IR."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v2_corpus_census as census
import response_analysis as analysis

controls,replay,parent=census.controls,census.replay,census.parent
CONFIG=ROOT/'audit/v2/response_audit.json'
TESTS=ROOT/'tests/unit/test_v2_response_audit.py'
FILES=[Path(__file__).resolve(),CONFIG,TESTS,ROOT/'audit/v2/response_analysis.py',ROOT/'audit/v2/RESPONSE_AUDIT.md',ROOT/'audit/v2/V2_EVALUATION_DESIGN.md']


def select(records,policy):
    cells=[c for record in records for c in record['model_cells']]
    missing=[c for c in cells if c['source']['route']=='serviceflow_ir' and c['analysis']['state']=='missing_saved_ir']
    selected=[c['source'] for c in missing if c['source'].get('original_method_status')=='parse_error']
    if (len(cells)!=policy['expected_original_cells'] or len(missing)!=policy['expected_missing_ir_cells']
            or len(selected)!=policy['expected_selected_cells'] or len({s['id'] for s in selected})!=len(selected)):
        raise ValueError('Original selection/denominators changed')
    if any(s['method'] not in ('m3','m4') for s in selected):raise ValueError('Unreviewed method response layout')
    ledger=[{'source':c['source'],'selected_for_response_audit':c['source'].get('original_method_status')=='parse_error',
             'state':'missing_saved_ir'} for c in missing]
    return selected,ledger


def local_response(root,stage):
    if not analysis.STAGE_RE.fullmatch(stage):raise ValueError('Unrecognized response stage')
    path=root/'responses'/(stage+'.txt')
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Response file escapes original cell directory')
    return path


def cell_inventory(source,policy):
    manifest=Path(source['manifest']);root=manifest.parent;document=replay.read_json(manifest)
    if (document.get('method',{}).get('id')!=source['method'] or document.get('sample_index')!=source['sample_index']
            or document.get('method_status')!='parse_error'):
        raise ValueError('Source manifest disagrees with fixed parse-error selection')
    paths=sorted((root/'responses').glob('*.txt'))
    if len(paths)>policy['max_attempts_per_cell']:raise ValueError('Response directory inspection limit')
    for path in paths:
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Saved response escapes original cell directory')
    inventory=analysis.inventory(document,[p.stem for p in paths],source['method'],policy['max_attempts_per_cell'])
    for row in inventory['attempts']:
        path=local_response(root,row['stage']);row['path']=str(path)
        row['source_sha256']=controls.sha256(path) if path.is_file() else 'MISSING'
    metadata={'harness_version':document.get('harness_version'),'prompt_version':document.get('prompt_version'),
        'runtime_compiler_version':document.get('runtime_compiler_version'),
        'original_repair_budget':document.get('repair',{}).get('budget') if isinstance(document.get('repair'),dict) else None,
        'recorded_method_error_end_of_stream_signal':any(t in str(document.get('method_error','')).lower() for t in ('end of stream','unexpected end'))}
    return {'source':source,**inventory,'recorded_metadata':metadata},[manifest,*paths,*[Path(a['path']) for a in inventory['attempts']]]


def prepare():
    policy=replay.read_json(CONFIG);root=ROOT/policy['parent_census'];previous=replay.read_json(root/'run.json')
    if previous['status']!='complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged corpus census is required')
    hashes=parent.verify_hashes(root,previous)
    records=census.read_checkpoints(previous,previous['cases'])
    sources,ledger=select(records,policy);inventories=[];extra=[]
    for source in sources:
        value,paths=cell_inventory(source,policy);inventories.append(value);extra.extend(paths)
    extra.extend([*FILES,root/'run.json',root/'input_sha256.json',ROOT/'src/prompt2serviceflow/experiments/extractors.py',ROOT/'schemas/serviceflow_ir.schema.json'])
    extra.extend(Path(s['path']) for s in previous['completed_cases'].values())
    for path in set(extra):
        name=str(path.resolve());digest=controls.sha256(path) if path.is_file() else 'MISSING'
        if name in hashes and hashes[name]!=digest:raise ValueError('Pinned prior input changed')
        hashes[name]=digest
    schema=replay.read_json(ROOT/'schemas/serviceflow_ir.schema.json')
    return policy,inventories,ledger,schema,hashes


def inspect(inventory,schema,policy):
    attempts=[];limited=False
    for original in inventory['attempts']:
        path=Path(original['path']);record=dict(original)
        if not path.is_file():record.update(text_state='missing_response_file',semantic_outcome='not_measured',extraction_repair_performed=False)
        elif path.stat().st_size>policy['max_response_bytes']:
            record.update(text_state='inspection_limit',bytes=path.stat().st_size);limited=True
        else:
            raw=path.read_bytes()
            if controls.sha256(path)!=original['source_sha256']:raise ValueError('Saved response changed since preflight')
            record.update(analysis.analyze_text(raw,record,schema,policy))
            limited|=record.get('candidate_inspection_limited',False)
        attempts.append(record)
    return {**inventory,'attempts':attempts,'state':'inspection_limit' if limited else 'audited',
            'llm_calls':0,'repairs':0,'semantic_outcome':'not_measured'}


def render(run,records,groups):
    lines=['# Saved-response availability and format audit','',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; selected parse-error missing-IR cells {len(run['inventories'])}.",
        f"Original missing-IR context ledger {len(run['availability_ledger'])}; zero LLM calls, extraction repairs, or semantic scores.",'',
        'Reported length stops and syntax end-of-stream signals are distinct observations; neither is an invented completion.',
        'Attempts retain recorded order; no earlier answer is substituted for the recorded terminal call.','',
        '## Model/method totals','',
        '| Model | Method | Cells | Attempts inspected | Terminal order unresolved | Any reported length stop |','|---|---|---:|---:|---:|---:|']
    for group in groups:
        lines.append(f"| {group['model']} | {group['method']} | {group['declared_cells']} | {sum(group['attempt_text_states'].values())} | {group['order_unresolved_cells']} | {group['length_stop_cells']} |")
    terminal=Counter()
    for group in groups:terminal.update(group['terminal_text_states'])
    lines+=['','## Terminal saved-text states (one per selected cell)','', '| State | Cells |','|---|---:|']
    lines.extend(f'| {state} | {n} |' for state,n in sorted(terminal.items()))
    wrappers=Counter()
    for group in groups:wrappers.update(group['wrapper_observations'])
    lines+=['','## Explicit presentation candidates (attempt-level, not recovered cells)','', '| Observation | Attempts |','|---|---:|']
    lines.extend(f'| {state} | {n} |' for state,n in sorted(wrappers.items()))
    lines+=['','A schema-conformant candidate is not contract-valid or semantically correct. No candidate is written as a submission.',
        'Empty text cannot be reconstructed from aggregate token counts; recorded zero reasoning tokens does not prove absence of reasoning.',
        'See responses.csv, cells.csv, response_diagnostics.json, grouped_counts.json, exact source/response fingerprints, and per-cell checkpoints.',
        'Original v1 results and the submitted paper remain unchanged. Any later repair/generation study needs its own frozen rules and accounting.','']
    return '\n'.join(lines)


def write_csv(output,records):
    fields=['cell','model','method','case','sample','stage','recorded_call_index','order_source','is_recorded_terminal','text_state','bytes',
            'reported_finish_reason','reported_length_stop','syntax_end_of_stream_signal','recorded_requested_max_tokens','completion_tokens','reasoning_tokens','wrapper_observation']
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for record in records:
        s=record['source']
        for a in record.get('attempts',[]):
            writer.writerow({'cell':s['id'],**{k:s[k] for k in ('model','method','case')},'sample':s['sample_index'],
                **{k:a.get(k) for k in fields[5:] if k not in ('completion_tokens','reasoning_tokens')},
                'completion_tokens':a.get('recorded_usage',{}).get('completion_tokens'),'reasoning_tokens':a.get('recorded_usage',{}).get('reasoning_tokens')})
    (output/'responses.csv').write_text(stream.getvalue())
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=['cell','model','method','case','sample','state','attempt_count','terminal_order_status','terminal_stage','terminal_text_state']);writer.writeheader()
    for record in records:
        s=record['source'];terminal=next((a for a in record.get('attempts',[]) if a.get('is_recorded_terminal')),None)
        writer.writerow({'cell':s['id'],**{k:s[k] for k in ('model','method','case')},'sample':s['sample_index'],'state':record['state'],
            'attempt_count':len(record.get('attempts',[])),'terminal_order_status':record.get('terminal_order_status'),
            'terminal_stage':record.get('terminal_stage'),'terminal_text_state':terminal['text_state'] if terminal else 'terminal_order_unresolved'})
    (output/'cells.csv').write_text(stream.getvalue())


def checkpoint_records(run):
    rows=[]
    for value in run['inventories']:
        identity=value['source']['id'];saved=run['completed_cells'][identity];path=Path(saved['path'])
        if controls.sha256(path)!=saved['sha256']:raise ValueError('Completed response checkpoint changed')
        row=replay.read_json(path)
        if row['source']!=value['source']:raise ValueError('Response checkpoint identity changed')
        rows.append(row)
    return rows


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv)
    print('Verifying the completed census and fixed parse-error response roster...',flush=True)
    policy,inventories,ledger,schema,hashes=prepare()
    if args.dry_run:
        print(json.dumps({'selected_cells':len(inventories),'original_missing_ir_context':len(ledger),
            'inventoried_response_attempts':sum(len(v['attempts']) for v in inventories),'llm_calls':0,'repairs':0,'workflow_executions':0,'semantic_scores':0},indent=2));return 0
    if args.resume:
        output=args.resume.resolve();run=replay.read_json(output/'run.json')
        if run['input_fingerprint']!=controls.fingerprint(hashes) or run['inventories']!=inventories or run['availability_ledger']!=ledger:
            raise ValueError('Response audit sources/metadata/code changed; cannot resume')
        if set(run['completed_cells'])-{v['source']['id'] for v in inventories}:raise ValueError('Unknown completed response cell')
        for saved in run['completed_cells'].values():
            if controls.sha256(Path(saved['path']))!=saved['sha256']:raise ValueError('Completed checkpoint changed')
    else:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');output=ROOT/'audit/outputs'/f'package_v2_response_audit__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True,exist_ok=False)
        run={'package_version':policy['package_version'],'audit_protocol_version':policy['audit_protocol_version'],'design':policy,'inventories':inventories,
             'availability_ledger':ledger,'completed_cells':{},'input_fingerprint':controls.fingerprint(hashes),'environment':controls.environment(),
             'llm_calls':0,'workflow_executions':0,'repairs':0,'semantic_scores':0}
        controls.write_json(output/'input_sha256.json',hashes);controls.write_json(output/'availability_ledger.json',ledger)
        for path in FILES:
            target=output/'implementation'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    run['status']='running';controls.write_json(output/'run.json',run);print(f'Output: {output}',flush=True)
    test=subprocess.run([sys.executable,'-m','pytest','-q',str(TESTS)],cwd=ROOT,capture_output=True,text=True,timeout=60)
    (output/'verification.txt').write_text(test.stdout+test.stderr)
    if test.returncode:
        run['status']='verification_failed';controls.write_json(output/'run.json',run);print(f'verification_failed: {output / "verification.txt"}',flush=True);return 1
    for number,value in enumerate(inventories,1):
        identity=value['source']['id']
        if identity in run['completed_cells']:continue
        try:record=inspect(value,schema,policy)
        except Exception as exc:record={**value,'state':'inspection_error','error_type':type(exc).__name__,'attempts':[]}
        target=output/'cells'/('attempt_'+uuid.uuid4().hex[:8])/'response_audit.json'
        controls.write_json(target,record);run['completed_cells'][identity]={'path':str(target),'sha256':controls.sha256(target)}
        controls.write_json(output/'run.json',run);print(f'[{number}/{len(inventories)}] {identity}: {record["state"]}',flush=True)
    records=checkpoint_records(run);groups=analysis.summarize(records)
    controls.write_json(output/'response_diagnostics.json',records);controls.write_json(output/'grouped_counts.json',groups);write_csv(output,records)
    try:parent.verify_hashes(output,run);unchanged=True
    except ValueError as exc:unchanged=False;run['integrity_error']=str(exc)
    errors=any(r['state'] in ('inspection_error','inspection_limit') for r in records)
    run['source_inputs_unchanged']=unchanged;run['status']='inputs_changed' if not unchanged else 'complete_with_errors' if errors else 'complete'
    controls.write_json(output/'run.json',run);(output/'summary.md').write_text(render(run,records,groups))
    print(run['status']+': '+str(output/'summary.md'),flush=True)
    return 0 if run['status']=='complete' else 1


if __name__=='__main__':raise SystemExit(main())
