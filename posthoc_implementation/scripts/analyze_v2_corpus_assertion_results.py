#!/usr/bin/env python3
"""Read and verify completed replay evidence; no inference or runtime execution.

Keep complete-suite scores separate from individual checks and output presence.
The original sample roster is the denominator for method-level results.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src'),str(ROOT/'audit/v2'),str(ROOT/'audit')]
import replay_v2_corpus_assertions_v2 as replay
import prepare_evaluation_final_results as statistics


def reason(check):
    if check['status']=='pass':return 'pass'
    if check['status']=='unscored_role_unresolved':return 'unresolved_output_role'
    if check['status']=='unscored_execution_error':return 'execution_error'
    message=check['message']
    if message.startswith('missing '):return 'missing_or_empty_output'
    if message.startswith('unexpected file '):return 'unexpected_output_in_absence_check'
    if message.startswith('JSONDecodeError:'):return 'output_not_valid_json'
    if message.startswith('KeyError:'):return 'missing_json_field'
    if message.startswith(('value=','length=','rows=')):return 'value_or_count_mismatch'
    return 'other_evaluation_error' if check['status']=='evaluation_error' else 'other_failed_check'


def positive_output(snapshot, original_path, selected_paths, types):
    """A required artifact is counted once per cell/scenario/reference path.

    Absence checks do not request a positive output. Never search for a file
    or infer a match from whether its contents satisfy a predicate.
    """
    row={'original_path':original_path,'selected_path':None,'state':'unresolved',
         'requires_json':any(t.startswith('json_') for t in types),'valid_json':None}
    if len(selected_paths)!=1 or None in selected_paths:return row
    path=next(iter(selected_paths));row['selected_path']=path
    actual=replay.engine.metadata.bounded.safe(snapshot,path)
    row['state']='present_nonempty' if actual.is_file() and actual.stat().st_size>0 else 'missing_or_empty'
    if row['state']=='present_nonempty' and row['requires_json']:
        try:json.loads(actual.read_text(encoding='utf-8'));row['valid_json']=True
        except (UnicodeError,ValueError):row['valid_json']=False
    return row


def summarize(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row['model'],row['method'])].append(row)
    summary=[]
    for (model,method),items in sorted(groups.items()):
        tasks=defaultdict(list)
        for row in items:tasks[row['case']].append(row)
        if len(items)!=330 or len(tasks)!=110 or any(len(v)!=3 for v in tasks.values()):raise ValueError('Incomplete model/method roster')
        report={'model':model,'method':method,'declared':len(items),'instances':len(tasks),
            'replayed':sum(r['replayed'] for r in items),'complete_execution':sum(r['complete_execution'] for r in items),
            'original_passes':sum(r['original_pass'] for r in items),
            'literal_passes':sum(r['literal_pass'] for r in items),'role_passes':sum(r['role_pass'] for r in items),
            'gained_original_to_role':sum(not r['original_pass'] and r['role_pass'] for r in items),
            'lost_original_to_role':sum(r['original_pass'] and not r['role_pass'] for r in items)}
        for key in ['original_pass','literal_pass','role_pass']:
            values=[sum(r[key] for r in repetitions)/3 for _,repetitions in sorted(tasks.items())]
            low,high=statistics.bca_mean(values,f'corpus_assertion_audit_d52c26ef/{model}/{method}/{key}')
            report[key+'_rate']=sum(values)/len(values);report[key+'_ci95']=[low,high]
        report['role_pass_given_replay']=report['role_passes']/report['replayed'] if report['replayed'] else None
        summary.append(report)
    return summary


def write_csv(path,rows):
    if not rows:raise ValueError('Expected nonempty result export')
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv);source=args.run.resolve();output=args.output.resolve()
    if not source.is_relative_to((ROOT/'audit/evaluator_only').resolve()):raise ValueError('Expected evaluator-only source')
    if output.is_relative_to(source):raise ValueError('Analysis must not modify sealed source evidence')
    print('Verifying immutable inputs, complete roster and saved replay seals; no inference or execution...',flush=True)
    prepared=replay.prepare();run=replay.read(source/'run.json');seal=replay.read(source/'output_sha256.json')
    if run['status']!='complete' or not run.get('source_inputs_unchanged') or not run['control_gate']['pass']:raise ValueError('Completed verified replay required')
    if run['design']!=prepared['design'] or run['input_fingerprint']!=replay.controls.fingerprint(prepared['hashes']):raise ValueError('Replay inputs differ')
    if replay.read(source/'input_sha256.json')!=prepared['hashes']:raise ValueError('Saved input pins differ')
    if run['plan_fingerprint']!=replay.previous.suite.adapter.digest(prepared['plan']) or replay.read(source/'plan.json')!=prepared['plan']:raise ValueError('Saved roster differs')
    replay.previous.previous.previous.verify_seal(source,seal)
    if set(run['completed_cells'])!={p['source']['id'] for p in prepared['plan']}:raise ValueError('Incomplete/foreign cell identities')
    records=[];checks=[];outputs=[];changes=[]
    for planned in prepared['plan']:
        identity=planned['source'];cell=replay.verify_checkpoint(run['completed_cells'][identity['id']],identity,source)
        directory=Path(run['completed_cells'][identity['id']]['path']).parent;replayed=cell['state']=='replayed'
        row={k:identity[k] for k in ['id','model','method','case','split','sample_index']}
        row.update({'admission':planned['admission'],'replayed':replayed,'complete_execution':replayed and cell['complete_scenario_coverage'] and not cell['execution_errors'],
            'original_pass':identity['published_semantic_success'] is True,'literal_pass':cell.get('reviewed_assertion_pass') is True,
            'role_pass':cell.get('role_matched_assertion_pass') is True})
        records.append(row)
        if row['original_pass']!=row['role_pass']:changes.append(row)
        if not replayed:continue
        assertions=replay.read(directory/'unchanged_assertions.json')
        definitions={(s['scenario'],a['assertion_id']):a for s in assertions['scenarios'] for a in s['assertions']}
        for scenario in cell['scenarios']:
            targets=defaultdict(lambda:{'paths':set(),'types':set()})
            if len(scenario['assertions'])!=len(scenario['role_matched_assertions']):raise ValueError('Paired assertion rosters differ')
            for condition,key in [('literal','assertions'),('output_role','role_matched_assertions')]:
                for check in scenario[key]:
                    definition=definitions[(scenario['scenario'],check['assertion_id'])]
                    path=definition['path'] if condition=='literal' else check['path_association']['path']
                    checks.append({'cell_id':identity['id'],'model':identity['model'],'method':identity['method'],
                        'case':identity['case'],'scenario':scenario['scenario'],'condition':condition,
                        'assertion_id':check['assertion_id'],'type':definition['type'],'original_path':definition['path'],
                        'selected_path':path,'status':check['status'],'category':reason(check),'message':check['message']})
                    if condition=='output_role' and definition['type']!='file_absent':
                        targets[definition['path']]['paths'].add(path);targets[definition['path']]['types'].add(definition['type'])
            for original,target in targets.items():
                item=positive_output(directory/'scenarios'/scenario['scenario']/'snapshot',original,target['paths'],target['types'])
                outputs.append({'cell_id':identity['id'],'model':identity['model'],'method':identity['method'],
                    'case':identity['case'],'scenario':scenario['scenario'],**item})
    if output.exists():raise ValueError('Refusing to overwrite an analysis output directory')
    output.mkdir(parents=True)
    summary=summarize(records)
    role=[c for c in checks if c['condition']=='output_role'];literal=[c for c in checks if c['condition']=='literal']
    totals={'declared':len(records),'replayed':sum(r['replayed'] for r in records),'complete_execution':sum(r['complete_execution'] for r in records),
        'original_passes':sum(r['original_pass'] for r in records),'literal_passes':sum(r['literal_pass'] for r in records),
        'role_passes':sum(r['role_pass'] for r in records),'gained':sum(not r['original_pass'] and r['role_pass'] for r in records),
        'lost':sum(r['original_pass'] and not r['role_pass'] for r in records),
        'literal_individual_checks':dict(Counter(c['category'] for c in literal)),
        'role_individual_checks':dict(Counter(c['category'] for c in role)),
        'positive_artifact_requirements':len(outputs),'positive_artifact_states':dict(Counter(o['state'] for o in outputs)),
        'required_json_present':sum(o['requires_json'] and o['state']=='present_nonempty' for o in outputs),
        'required_json_parseable':sum(o['valid_json'] is True for o in outputs),'llm_calls':0,'runtime_executions':0}
    for name,rows in [('run_level.csv',records),('assertion_level.csv',checks),('positive_outputs.csv',outputs),('score_changes.csv',changes)]:write_csv(output/name,rows)
    replay.engine.write(output/'results.json',{'totals':totals,'methods':summary})
    lines=['# Execution and held-out output assertion audit','','All original M3–M5 cells are retained. Complete-suite rates use all 330 runs per model/method. The 797 replayed cells were selected because they already passed the original public gates. Their execution completion is a conditional diagnostic, not a new full-corpus method success rate.','',
        '| Model | Method | Replayed | Original passes / 330 | Literal / 330 | Role-matched / 330 | Role-matched rate [95% BCa CI] |',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in summary:
        low,high=r['role_pass_ci95'];lines.append(f"| {r['model']} | {r['method']} | {r['replayed']} | {r['original_passes']} | {r['literal_passes']} | {r['role_passes']} | {100*r['role_pass_rate']:.1f}% [{100*low:.1f}, {100*high:.1f}] |")
    lines+=['','Intervals resample 110 pipeline instances after averaging their three repetitions, using the existing paper analysis function. No new confirmatory significance claim is made.','',
        '```json',json.dumps(totals,indent=2),'```','',
        'Individual assertion pass rates and artifact presence have different denominators from complete-suite success. They describe failure modes and must not replace the complete-suite metric. The output requirements count unique positive reference paths per replayed cell/scenario; absence predicates remain in the assertion table. Unresolved paths remain visible.','',
        'The original compiler executes deterministic mocks: schema examples when a schema is available, otherwise generic text for many output types, and fixture copying for CSV/table outputs. This audit measures those implementations under the unchanged held-out predicates. Scope the paper to execution and checked outputs; do not describe these as real-service task completion.','',
        'The path association is evaluator-only and uses reviewed reference service/port roles. Expected values, operators, source programs and snapshots are unchanged. It is a separately labeled post-hoc correction, not an additional model-generated answer.','']
    (output/'summary.md').write_text('\n'.join(lines))
    provenance={'source_run':str(source),'source_output_fingerprint':seal['output_fingerprint'],'verified_source_files':len(seal['files']),
        'verified_input_pins':len(prepared['hashes']),'analysis_script_sha256':replay.controls.sha256(Path(__file__)),
        'statistics_script_sha256':replay.controls.sha256(Path(statistics.__file__)),'created_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Execution and output assertion analysis; no inference or runtime execution; original paper and results untouched'}
    replay.engine.write(output/'provenance.json',provenance)
    replay.engine.write(output/'SHA256.json',replay.engine.files(output))
    print('complete: '+str(output/'summary.md'),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
