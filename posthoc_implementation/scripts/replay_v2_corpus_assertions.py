#!/usr/bin/env python3
"""Manual, zero-LLM corpus replay with corrected scenario coverage and snapshots."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts'), str(ROOT / 'audit/v2'), str(ROOT / 'audit')]
import run_v2_reviewed_scenarios as previous
import audit_v2_output_trace as trace
import corpus_assertion_replay as engine

controls, read = previous.controls, previous.replay.read_json
CONFIG = ROOT / 'audit/v2/corpus_assertion_replay.v1.json'
TEST = ROOT / 'tests/unit/test_v2_corpus_assertion_replay.py'
DOC = ROOT / 'audit/v2/CORPUS_ASSERTION_REPLAY.md'
IMPLEMENTATION = [CONFIG, TEST, DOC, Path(__file__).resolve(), Path(engine.__file__)]


def verify_inputs(directory, run):
    return previous.previous.previous.previous.prior.previous.coverage.frozen.parent.verify_hashes(directory, run)


def prepare():
    design = read(CONFIG)
    if design['llm_requests_permitted'] != 0: raise ValueError('No inference allowed')
    lock_path = ROOT / design['freeze_lock']; lock = read(lock_path)
    if lock['protocol_version'] != design['protocol_version']: raise ValueError('Freeze version differs')
    previous.previous.previous.verify_named_inputs(ROOT, lock['files'], [p.relative_to(ROOT).as_posix() for p in IMPLEMENTATION])
    parent = ROOT / design['parent_run']; old = read(parent / 'run.json')
    if old['status'] != 'complete' or not old.get('source_inputs_unchanged') or not old['suite_summary']['suite_pass']: raise ValueError('Verified reviewed-scenario pilot required')
    hashes = verify_inputs(parent, old); seal = read(parent / 'output_sha256.json')
    previous.previous.previous.verify_seal(parent, seal)
    if seal['output_fingerprint'] != design['parent_output_fingerprint']: raise ValueError('Pilot evidence differs')
    paths = [*IMPLEMENTATION, lock_path, Path(trace.__file__), parent / 'output_sha256.json', *[parent / n for n in seal['files']]]
    attribution = ROOT / design['attribution_run']; record = read(attribution / 'run.json')
    if record['status'] != 'complete' or not record.get('source_inputs_unchanged'): raise ValueError('Completed attribution required')
    for checkpoint in record['result_files'].values():
        for relative, sha in checkpoint['files'].items():
            path = Path(checkpoint['path']).parent / relative
            if controls.sha256(path) != sha: raise ValueError('Attribution evidence changed')
            paths.append(path)
    rows = read(attribution / 'evidence/cells.json'); rows = sorted(rows, key=lambda r: r['id'])
    if len(rows) != design['expected_cells'] or len({r['id'] for r in rows}) != len(rows): raise ValueError('Original IR roster differs')
    cases = sorted({r['case'] for r in rows})
    if len(cases) != design['expected_cases'] or dict(Counter(c.split('/')[0] for c in cases)) != design['expected_strata']: raise ValueError('Task roster differs')
    if sum(r['published_executable_valid'] is True for r in rows) != design['expected_public_valid_cells']: raise ValueError('Original public-valid selection differs')
    contexts = {}; directories = {}; plan = []
    for case in cases:
        instance = ROOT / 'benchmark/instances' / case
        runtime = engine.metadata.document(instance / 'runtime/manifest.yaml'); assertions = engine.metadata.document(instance / 'gold/assertions.yaml')
        engine.scenario_roster(runtime, assertions)
        contexts[case] = str(instance)
        paths.extend([instance / 'runtime/manifest.yaml', instance / 'gold/assertions.yaml'])
        directory = instance / 'fixtures'; tree = engine.metadata.tree(directory); directories[str(directory)] = tree
        paths.extend(engine.metadata.bounded.safe(directory, name) for name in tree['files'])
    for source in rows:
        row = {'source': source, 'submission': str(Path(source['saved_ir_path']).parent), 'instance': contexts[source['case']],
               'admission': 'not_replayed_original_public_invalid'}
        if not source['saved_ir_present']: row['admission'] = 'missing_saved_ir'
        elif source['published_executable_valid'] is True:
            submission = Path(row['submission']); path = submission / 'runtime/manifest.yaml'; paths.append(path)
            if not path.is_file(): row['admission'] = 'missing_saved_runtime'
            else:
                runtime = engine.metadata.document(path); recognized = trace.scan_runtime(submission, runtime, 2097152)
                row['writer_plan'] = recognized
                row['admission'] = 'eligible_frozen_mock' if recognized['complete_recognized_writer_plan'] else 'unsupported_runtime'
                for script in runtime.get('tasks', []): paths.append(trace.local(submission / 'runtime', script['script']))
        plan.append(row)
    for path in paths:
        key = str(path.resolve()); sha = controls.sha256(path) if path.is_file() else 'MISSING'
        if key in hashes and hashes[key] != sha: raise ValueError('Pinned input changed: ' + key)
        hashes[key] = sha
    return {'design': design, 'plan': plan, 'hashes': hashes, 'directory_inventories': directories}


def control_gate(root):
    root.mkdir(parents=True)
    program = '''import argparse,json\nfrom pathlib import Path\np=argparse.ArgumentParser()\np.add_argument('--workspace');p.add_argument('--fixtures');p.add_argument('--pick')\na=p.parse_args();v=json.loads((Path(a.fixtures)/a.pick).read_text())\no=Path(a.workspace)/'artifacts';o.mkdir()\n(o/'value.json').write_text(json.dumps(v))\n'''
    instance = root / 'authored'; (instance / 'runtime/scripts').mkdir(parents=True)
    (instance / 'runtime/scripts/run.py').write_text(program)
    (instance / 'fixtures/inputs').mkdir(parents=True)
    engine.write(instance / 'fixtures/inputs/a.json', {'value': True}); engine.write(instance / 'fixtures/inputs/b.json', {'value': False})
    runtime = {'tasks': [{'intent_id': 'read', 'script': 'scripts/run.py', 'arguments': ['--workspace','{workspace}','--fixtures','{fixtures}','--pick','{chosen}']}],
        'scenarios': [{'name': n, 'parameters': {'chosen': f}, 'fixture_root': 'fixtures/inputs'} for n, f in [('first','a.json'),('second','b.json')]]}
    assertions = {'scenarios': [{'scenario': n, 'assertions': [{'assertion_id': 'value', 'type': 'json_path_equals','path':'artifacts/value.json','json_path':'value','expected': v}]} for n,v in [('first',True),('second',False)]]}
    engine.write(instance / 'runtime/manifest.yaml', runtime); engine.write(instance / 'gold/assertions.yaml', assertions)
    genuine = engine.replay(instance, instance, root / 'genuine', 'authored/control')
    missing_detected = not engine.complete(['first','second'], genuine['scenarios'][:1])
    duplicate_detected = not engine.complete(['first','second'], genuine['scenarios'] + genuine['scenarios'][:1])
    reused = {'scenario': 'second', '_errors': []}
    wrong = engine.score(root / 'genuine/scenarios/first/snapshot', reused, assertions['scenarios'][1]['assertions'])
    result = {'positive_gate': genuine['reviewed_assertion_pass'], 'missing_detected': missing_detected,
              'duplicate_detected': duplicate_detected, 'positive_reuse_detected': not wrong['reviewed_assertion_pass']}
    result['pass'] = all(result.values()); engine.write(root / 'result.json', result); return result


def checkpoint(directory, source, result):
    result['source'] = source
    result['evidence_files'] = engine.files(directory)
    engine.write(directory / 'result.json', result)
    return {'path': str(directory / 'result.json'), 'sha256': controls.sha256(directory / 'result.json')}


def verify_checkpoint(check, source):
    path = Path(check['path']); result = read(path)
    if controls.sha256(path) != check['sha256'] or result['source'] != source: raise ValueError('Cell identity/hash changed')
    actual = engine.files(path.parent); actual.pop('result.json')
    if actual != result['evidence_files']: raise ValueError('Cell snapshots changed')
    return result


def render(output, run, plan):
    results = [verify_checkpoint(run['completed_cells'][p['source']['id']], p['source']) for p in plan if p['source']['id'] in run['completed_cells']]
    aggregate = {'declared_cells': len(plan), 'completed_cells': len(results), 'pending_cells': len(plan)-len(results),
                 'admission_states': dict(Counter(p['admission'] for p in plan)), 'states': dict(Counter(r['state'] for r in results)),
                 'original_published_passes': sum(p['source']['published_semantic_success'] is True for p in plan),
                 'corrected_reviewed_assertion_passes': sum(r.get('reviewed_assertion_pass') is True for r in results),
                 'real_business_semantics_verified_by_this_replay': 0, 'llm_calls': 0}
    engine.write(output / 'aggregate.json', aggregate)
    lines = ['# Corpus reviewed-assertion replay', '', 'Status: '+run['status'], '', run['design']['scope'], '',
             '```json', json.dumps(aggregate,indent=2), '```', '',
             '| Model | Method | Declared | Completed | Replayed | Reviewed-assertion passes |', '|---|---|---:|---:|---:|---:|']
    for model, method in sorted({(p['source']['model'],p['source']['method']) for p in plan}):
        declared=[p for p in plan if p['source']['model']==model and p['source']['method']==method]
        done=[r for r in results if r['source']['model']==model and r['source']['method']==method]
        lines.append(f"| {model} | {method} | {len(declared)} | {len(done)} | {sum(r['state']=='replayed' for r in done)} | {sum(r.get('reviewed_assertion_pass') is True for r in done)} |")
    lines += ['', 'All replayed source programs are recognized frozen mock implementations. These counts do not certify real business transformations.',
              'Compare the original baseline and this corrected scenario/predicate condition separately. Keep the real PostgreSQL pilot and other real-execution v2 studies separate.',
              'No new LLM generation, source edits, predicate relaxation, artifact renaming or original-score overwrite occurred.', '']
    (output/'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dry-run',action='store_true');parser.add_argument('--resume',type=Path);args=parser.parse_args(argv)
    print('Verifying all original IR identities and corrected reviewed-scenario inputs; no LLM calls...',flush=True)
    p=prepare();d=p['design'];fingerprint=previous.suite.adapter.digest(p['plan'])
    if args.dry_run:
        print(json.dumps({'declared_cells':len(p['plan']),'cases':110,'admission':dict(Counter(r['admission'] for r in p['plan'])),
                          'verified_input_pins':len(p['hashes']),'llm_calls':0,'runtime_executions':0},indent=2));return 0
    if args.resume:
        output=args.resume.resolve()
        if not output.is_relative_to((ROOT/'audit/evaluator_only').resolve()):raise ValueError('Resume must stay in evaluator_only')
        run=read(output/'run.json')
        if (run['design']!=d or run['input_fingerprint']!=controls.fingerprint(p['hashes']) or run['plan_fingerprint']!=fingerprint
                or read(output/'input_sha256.json')!=p['hashes'] or previous.suite.adapter.digest(read(output/'plan.json'))!=fingerprint):raise ValueError('Immutable resume design differs')
        if (output/'output_sha256.json').exists():previous.previous.previous.verify_seal(output,read(output/'output_sha256.json'))
        if not set(run['completed_cells'])<={x['source']['id'] for x in p['plan']}:raise ValueError('Foreign completed cell')
        for row in p['plan']:
            if row['source']['id'] in run['completed_cells']:verify_checkpoint(run['completed_cells'][row['source']['id']],row['source'])
    else:
        output=ROOT/'audit/evaluator_only'/('package_v2_corpus_assertions__'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'__'+uuid.uuid4().hex[:8]);output.mkdir(parents=True)
        run={'status':'prepared','design':d,'completed_cells':{},'input_fingerprint':controls.fingerprint(p['hashes']),'plan_fingerprint':fingerprint,'llm_calls':0,'evidence_role':'evaluator_only_never_model_context'}
        engine.write(output/'input_sha256.json',p['hashes']);engine.write(output/'plan.json',p['plan']);engine.write(output/'run.json',run)
    print('Output: '+str(output),flush=True)
    try:
        tests=subprocess.run([sys.executable,'-m','pytest','-q',str(TEST)],cwd=ROOT,capture_output=True,text=True,timeout=90)
        (output/('verification_'+uuid.uuid4().hex[:8]+'.txt')).write_text(tests.stdout+tests.stderr)
        if tests.returncode:raise ValueError('Synthetic evaluator verification failed')
        gate=control_gate(output/('controls_'+uuid.uuid4().hex[:8]));run['control_gate']=gate
        if not gate['pass']:raise ValueError('Scenario handoff control failed; no corpus programs replayed')
        run['status']='running'
        for row in p['plan']:
            source=row['source'];name=source['id']
            if name in run['completed_cells']:continue
            directory=output/'cells'/name/('attempt_'+uuid.uuid4().hex[:8]);directory.parent.mkdir(parents=True,exist_ok=True)
            if row['admission']!='eligible_frozen_mock':
                directory.mkdir();result={'state':row['admission'],'reviewed_assertion_pass':None,'business_semantics_verified':False}
            else:
                result=engine.replay(Path(row['submission']),Path(row['instance']),directory,name,timeout=d['task_timeout_s'])
            run['completed_cells'][name]=checkpoint(directory,source,result);engine.write(output/'run.json',run)
            print(f"{len(run['completed_cells'])}/{len(p['plan'])} {name}: {result['state']}",flush=True)
        verify_inputs(output,run)
        previous.previous.verify_directories(p['directory_inventories']);run['source_inputs_unchanged']=True
        run['status']='complete'
    except BaseException as exc:
        run['status']='interrupted_or_error';run['error']=type(exc).__name__+': '+str(exc)[:1500]
        engine.write(output/'run.json',run);render(output,run,p['plan']);previous.previous.seal_output(output);raise
    engine.write(output/'run.json',run);render(output,run,p['plan']);previous.previous.seal_output(output)
    print('complete: '+str(output/'summary.md'),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
