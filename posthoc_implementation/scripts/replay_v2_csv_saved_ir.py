#!/usr/bin/env python3
"""User-run frozen 54-cell saved IR study; no inference or generated programs."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'audit/v2')); sys.path.insert(0, str(ROOT / 'audit'))
import run_v2_csv_ir_adapter_controls as previous
import csv_saved_replay as analysis

controls, replay = previous.controls, previous.replay
adapter, oracle, transport = previous.adapter, previous.oracle, previous.transport
CONFIG = ROOT / 'audit/v2/csv_saved_replay.v1.json'
TEST = ROOT / 'tests/unit/test_v2_csv_saved_replay.py'
DOC = ROOT / 'audit/v2/CSV_SAVED_REPLAY.md'


def verify_seal(directory, seal):
    if controls.fingerprint(seal['files']) != seal['output_fingerprint']: raise ValueError('Output seal fingerprint differs')
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(seal['files']) | {seal['self_excluded']}: raise ValueError('Sealed evidence roster differs')
    for relative, sha in seal['files'].items():
        if controls.sha256(analysis.public.safe(directory, relative)) != sha: raise ValueError('Sealed evidence changed: ' + relative)


def verify_named_inputs(root, files, expected):
    if set(files) != set(expected): raise ValueError('Frozen implementation roster differs')
    for relative, digest in files.items():
        if controls.sha256(analysis.public.safe(root, relative)) != digest:
            raise ValueError('Frozen implementation changed: ' + relative)


def prepare():
    design = replay.read_json(CONFIG)
    if design['adapter_version'] != adapter.VERSION: raise ValueError('Adapter version differs')
    implementation = [CONFIG, TEST, DOC, Path(__file__).resolve(), Path(analysis.__file__)]
    lock_path = ROOT / design['freeze_lock']; lock = replay.read_json(lock_path)
    if lock['protocol_version'] != design['protocol_version']: raise ValueError('Freeze protocol differs')
    verify_named_inputs(ROOT, lock['files'], [p.relative_to(ROOT).as_posix() for p in implementation])
    parent = ROOT / design['controls_run']; old = replay.read_json(parent / 'run.json')
    if old['status'] != 'complete' or old.get('source_inputs_unchanged') is not True or old['llm_calls'] or old['saved_workflows_executed']:
        raise ValueError('Completed unchanged authored controls required')
    hashes = previous.prior.previous.coverage.frozen.parent.verify_hashes(parent, old)
    seal = replay.read_json(parent / 'output_sha256.json'); verify_seal(parent, seal)
    if seal['output_fingerprint'] != design['controls_output_fingerprint']: raise ValueError('Control evidence differs from declared freeze')
    review_path = ROOT / design['controls_review']; review = replay.read_json(review_path)
    if review['output_fingerprint'] != seal['output_fingerprint'] or not all(c['all_checks_verified'] for c in review['cases']):
        raise ValueError('Reviewed control evidence differs')
    cases = {s['case']: s for s in design['cases']}
    if {c['case'] for c in old['case_results']} != set(cases) or not all(c['control_gate_pass'] for c in old['case_results']):
        raise ValueError('Both authored control gates must pass')
    paths = [*implementation, lock_path, review_path,
             parent / 'output_sha256.json', *[parent / r for r in seal['files']]]
    eligibility = ROOT / old['design']['eligibility_run']; inventory = replay.read_json(eligibility / 'run.json')
    previous.prior.verify_roster(inventory['sources'], inventory['design'])
    source_map = {s['id']: s for s in inventory['sources']}
    roster = list(itertools.product(design['models'], design['methods'], cases, design['samples']))
    sources = [source_map['/'.join(map(str, x))] for x in roster]
    if len(sources) != design['expected_ir_cells'] or len({s['id'] for s in sources}) != len(sources): raise ValueError('IR roster differs')
    backlog = [s for s in inventory['sources'] if s['route'] == 'direct_argo']
    if len(backlog) != design['expected_direct_argo_backlog']: raise ValueError('Direct-Argo roster differs')
    for name, checkpoint in inventory['completed_cells'].items():
        path = Path(checkpoint['path'])
        if controls.sha256(path) != checkpoint['sha256'] or replay.read_json(path)['source']['id'] != name:
            raise ValueError('Original eligibility checkpoint changed')
        paths.append(path)
    baseline = ROOT / old['design']['public_baseline']; contexts = {}
    for case, spec in cases.items():
        workspace = baseline / case / 'public_workspace' / case
        schema = replay.read_json(workspace / 'schemas/serviceflow_ir.schema.json'); previous.prior.local_schema(schema)
        contexts[case] = {'workspace': str(workspace), 'schema': schema, 'source_csv': spec['source_csv']}
        # Pin the complete public file inventory, including resources that are
        # absent from an individual IR. No private reference/assertion is read.
        paths.extend(p for p in workspace.rglob('*') if p.is_file())
    for path in paths:
        key, value = str(path.resolve()), controls.sha256(path)
        if key in hashes and hashes[key] != value: raise ValueError('Frozen input changed: ' + key)
        hashes[key] = value
    rows = []
    for source in sources:
        row = analysis.inspect(source, contexts[source['case']], design)
        expected = hashes.get(str(Path(source['artifact']).resolve()))
        if row['artifact_sha256'] != expected: raise ValueError('Original artifact changed: ' + source['id'])
        rows.append(row)
    return {'design': design, 'hashes': hashes, 'rows': rows, 'direct_argo_backlog': backlog,
            'image': old['image'], 'expected_server_version': old['server_version']}


def snapshot_files(directory):
    return {p.relative_to(directory).as_posix(): controls.sha256(p) for p in directory.rglob('*') if p.is_file()}


def checkpoint(directory, row, result):
    result.update(source=row['source'], artifact_sha256=row['artifact_sha256'], admission_state=row['state'], findings=row['findings'])
    result['evidence_files'] = snapshot_files(directory)
    controls.write_json(directory / 'result.json', result)
    return {'path': str(directory / 'result.json'), 'sha256': controls.sha256(directory / 'result.json')}


def verify_checkpoint(saved, row):
    path = Path(saved['path']); result = replay.read_json(path)
    if controls.sha256(path) != saved['sha256'] or result['source'] != row['source'] or result['artifact_sha256'] != row['artifact_sha256']:
        raise ValueError('Cell checkpoint identity/hash differs')
    actual = snapshot_files(path.parent); actual.pop('result.json')
    if actual != result['evidence_files']: raise ValueError('Cell evidence changed')
    return result


def validate_resume(output, run, prepared, image):
    rows, design = prepared['rows'], prepared['design']
    frozen = {'rows': rows, 'direct_argo_backlog': prepared['direct_argo_backlog']}
    fingerprint = adapter.digest(frozen)
    if (run['input_fingerprint'] != controls.fingerprint(prepared['hashes']) or run['frozen_plan_sha256'] != fingerprint
            or run['image']['id'] != image['id'] or run['design'] != design):
        raise ValueError('Resume differs from the immutable replay design')
    if replay.read_json(output / 'input_sha256.json') != prepared['hashes']:
        raise ValueError('Saved input hash manifest changed')
    if adapter.digest(replay.read_json(output / 'frozen_plan.json')) != fingerprint: raise ValueError('Saved frozen plan changed')
    if (output / 'output_sha256.json').exists(): verify_seal(output, replay.read_json(output / 'output_sha256.json'))
    if not set(run['completed_cells']) <= {r['source']['id'] for r in rows}: raise ValueError('Undeclared completed cell')
    for row in rows:
        name = row['source']['id']
        if name not in run['completed_cells']: continue
        saved = run['completed_cells'][name]
        if not Path(saved['path']).resolve().is_relative_to((output / 'cells' / name).resolve()):
            raise ValueError('Cell evidence outside its assigned directory')
        verify_checkpoint(saved, row)


def database_infrastructure_failure(error):
    # Treat unrecognized/environment failures conservatively as pending
    # infrastructure. Data, constraint and object/statement errors can be
    # recorded as completed operation failures without attributing them to an LLM.
    return error.sqlstate is None or error.sqlstate[:2] not in ('22', '23', '42', '0A')


def run_trial(row, scenario, directory, image):
    directory.mkdir(parents=True, exist_ok=False)
    plan, raw = analysis.materialize(row, directory / 'fixtures', scenario)
    controls.write_json(directory / 'plan.json', plan)
    if raw is not None: (directory / 'expected.csv').write_bytes(raw)
    target = row['target']; before = after = receipt = None; failure = None
    with transport.Postgres(image) as database:
        database.sql('CREATE SCHEMA IF NOT EXISTS ' + adapter.ops.ident(target['schema']))
        before = oracle.observe(database, target['schema'], target['table']); controls.write_json(directory / 'before.json', before)
        try: receipt = adapter.execute(plan, database, directory / 'fixtures', directory / 'execution')
        except adapter.Error as exc: failure = {'code': exc.code, 'message': str(exc)}
        except FileNotFoundError as exc:
            if scenario != 'missing_file': raise
            failure = {'code': 'ungated_missing_csv', 'message': str(exc)}
        except transport.DatabaseError as exc:
            if database_infrastructure_failure(exc): raise
            failure = {'code': 'database_operation_error', 'sqlstate': exc.sqlstate, 'message': str(exc)}
        after = oracle.observe(database, target['schema'], target['table']); controls.write_json(directory / 'after.json', after)
        (directory / 'target.sql').write_text(transport.docker('exec', database.name, 'pg_dump', '-U', 'postgres', '-d', 'p2sf_controls',
            '--schema=' + target['schema'], '--no-owner', '--no-privileges'))
        checked = analysis.evaluate(scenario, raw, receipt, failure, before, after)
        checked.update(scenario=scenario, receipt=receipt, failure=failure, server_version=database.server_version,
                       source_ir_unchanged=adapter.digest(plan['source_ir']) == row['plan']['source_ir_sha256'])
        checked['pass'] = checked['pass'] and checked['source_ir_unchanged']
        controls.write_json(directory / 'result.json', checked)
        return checked


def run_cell(row, directory, image, design):
    directory.mkdir(parents=True, exist_ok=False)
    if row['state'] != 'admitted':
        return checkpoint(directory, row, {'state': row['state'], 'business_suite_pass': None, 'nominal_business_pass': None, 'trials': []})
    source = Path(row['source']['artifact']); raw = source.read_bytes()
    if analysis.sha(raw) != row['artifact_sha256']: raise ValueError('Original source changed before replay')
    (directory / 'original_saved_ir.yaml').write_bytes(raw)
    controls.write_json(directory / 'admitted_plan.json', row['plan'])
    trials = [run_trial(row, name, directory / 'trials' / name, image) for name in design['positive_trials'] + design['negative_trials']]
    return checkpoint(directory, row, {'state': 'replayed', 'business_suite_pass': all(t['pass'] for t in trials),
        'nominal_business_pass': next(t['pass'] for t in trials if t['scenario'] == 'nominal'),
        'trials': [{k: t[k] for k in ('scenario', 'pass', 'checks', 'failure')} for t in trials],
        'plan_sha256': row['plan']['plan_sha256']})


def render(output, run, rows):
    completed = {row['source']['id']: verify_checkpoint(run['completed_cells'][row['source']['id']], row)
                 for row in rows if row['source']['id'] in run['completed_cells']}
    states = Counter(r['state'] for r in rows); results = list(completed.values())
    summary = {'declared_ir_cells': len(rows), 'available_ir': sum(r['artifact_sha256'] != 'MISSING' for r in rows),
        'admission_states': dict(states), 'completed_cells': len(results), 'pending_cells': len(rows) - len(results),
        'replayed_cells': sum(r['state'] == 'replayed' for r in results), 'nominal_business_passes': sum(r['nominal_business_pass'] is True for r in results),
        'business_suite_passes': sum(r['business_suite_pass'] is True for r in results), 'direct_argo_backlog': 54,
        'infrastructure_attempts': len(run['infrastructure_attempts'])}
    controls.write_json(output / 'aggregate.json', summary)
    lines = ['# Frozen saved CSV IR replay', '', 'Status: ' + run['status'], '', run['design']['scope'], '',
        '| Coverage | Cells |', '|---|---:|']
    lines += ['| ' + k + ' | ' + str(v) + ' |' for k, v in summary.items() if not isinstance(v, dict)]
    lines += ['', '## Admission', '', '| State | Cells |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in sorted(states.items())]
    lines += ['', '## Model/method coverage', '', '| Model | Method | Declared | Missing | Blocked | Admitted | Replayed | Nominal pass | All five probes pass |', '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for model, method in itertools.product(run['design']['models'], run['design']['methods']):
        group = [r for r in rows if r['source']['model'] == model and r['source']['method'] == method]
        done = [completed[r['source']['id']] for r in group if r['source']['id'] in completed]
        numbers = [len(group), sum(r['state'] == 'missing' for r in group), sum(r['state'] == 'blocked' for r in group),
                   sum(r['state'] == 'admitted' for r in group), sum(r['state'] == 'replayed' for r in done),
                   sum(r['nominal_business_pass'] is True for r in done), sum(r['business_suite_pass'] is True for r in done)]
        lines.append('| ' + model + ' | ' + method + ' | ' + ' | '.join(map(str, numbers)) + ' |')
    codes = Counter((f['category'], f['code']) for r in rows for f in r['findings'])
    lines += ['', '## Admission findings', '', '| Category | Code | Findings |', '|---|---|---:|']
    lines += [f'| {c} | {k} | {n} |' for (c, k), n in sorted(codes.items())]
    lines += ['', 'Pass counts apply only to this bounded business-operation condition. Missing/blocked cells remain in the declared 54-cell coverage.',
        'No corpus-wide semantic-success rate, full Argo or public M5 tool-route equivalence is claimed. Original v1 scores are unchanged.',
        'Each admitted cell has three positive CSV trials and two rejection/gating trials. Every trial starts a fresh isolated database.',
        'Inspect frozen_plan.json, direct_argo_backlog.json, input/output hashes, per-cell evidence and infrastructure attempts.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def seal_output(output):
    files = snapshot_files(output); files.pop('output_sha256.json', None)
    controls.write_json(output / 'output_sha256.json', {'files': files, 'output_fingerprint': controls.fingerprint(files),
        'seal_stage': 'end-of-invocation', 'self_excluded': 'output_sha256.json'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path); parser.add_argument('--postgres-image'); args = parser.parse_args(argv)
    print('Verifying frozen controls and inspecting all 54 original IR cells (no inference)...', flush=True)
    p = prepare(); rows, design = p['rows'], p['design']
    if args.dry_run:
        print(json.dumps({'declared_ir_cells': len(rows), 'admission_states': dict(Counter(r['state'] for r in rows)),
            'direct_argo_backlog': len(p['direct_argo_backlog']), 'trials_per_admitted_cell': 5, 'verified_input_pins': len(p['hashes']),
            'llm_calls': 0, 'saved_output_executions': 0}, indent=2)); return 0
    image = transport.image_info(args.postgres_image or p['image']['id'])
    if image['id'] != p['image']['id']: raise ValueError('Use the exact PostgreSQL image tested by the frozen controls')
    frozen = {'rows': rows, 'direct_argo_backlog': p['direct_argo_backlog']}; fingerprint = adapter.digest(frozen)
    if args.resume:
        output = args.resume.resolve()
        if not output.is_relative_to((ROOT / 'audit/outputs').resolve()): raise ValueError('Resume directory must be in audit/outputs')
        run = replay.read_json(output / 'run.json')
        validate_resume(output, run, p, image)
    else:
        output = ROOT / 'audit/outputs' / ('package_v2_csv_saved_replay__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        run = {'status': 'prepared', 'design': design, 'image': image, 'completed_cells': {}, 'infrastructure_attempts': [],
               'llm_calls': 0, 'input_fingerprint': controls.fingerprint(p['hashes']), 'frozen_plan_sha256': fingerprint,
               'environment': {'python': sys.version, 'jsonschema': importlib.metadata.version('jsonschema'), 'PyYAML': importlib.metadata.version('PyYAML')}}
        controls.write_json(output / 'frozen_plan.json', frozen); controls.write_json(output / 'direct_argo_backlog.json', p['direct_argo_backlog'])
        controls.write_json(output / 'input_sha256.json', p['hashes']); controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    try:
        env = dict(os.environ); env['P2SF_POSTGRES_TEST_IMAGE'] = image['id']
        tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TEST)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        (output / ('verification_' + uuid.uuid4().hex[:8] + '.txt')).write_text(tests.stdout + tests.stderr)
        if tests.returncode: raise ValueError('Synthetic replay verification failed')
        run['status'] = 'running'; controls.write_json(output / 'run.json', run)
        for row in rows:
            name = row['source']['id']
            if name in run['completed_cells']: continue
            directory = output / 'cells' / name / ('attempt_' + uuid.uuid4().hex[:8])
            try:
                saved = run_cell(row, directory, image, design)
                run['completed_cells'][name] = saved
                result = replay.read_json(Path(saved['path']))
                print(name + ': ' + result['state'] + ', suite=' + str(result['business_suite_pass']), flush=True)
            except (transport.DatabaseError, OSError, subprocess.TimeoutExpired) as exc:
                failure = {'source_id': name, 'attempt_directory': str(directory), 'type': type(exc).__name__, 'message': str(exc)[:2000]}
                controls.write_json(directory / 'infrastructure_error.json', failure); run['infrastructure_attempts'].append(failure)
                print(name + ': infrastructure attempt retained; cell pending', flush=True)
            controls.write_json(output / 'run.json', run)
        previous.prior.previous.coverage.frozen.parent.verify_hashes(output, run); run['source_inputs_unchanged'] = True
        run['status'] = 'complete' if len(run['completed_cells']) == len(rows) else 'pending_infrastructure'
    except BaseException as exc:
        run['status'] = 'interrupted_or_error'; run['error'] = type(exc).__name__ + ': ' + str(exc)[:1000]
        controls.write_json(output / 'run.json', run); render(output, run, rows); seal_output(output); raise
    controls.write_json(output / 'run.json', run); render(output, run, rows); seal_output(output)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    if run['status'] != 'complete': print('Resume with --resume ' + str(output), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
