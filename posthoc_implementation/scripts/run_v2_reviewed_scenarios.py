#!/usr/bin/env python3
"""User-run v2 reviewed scenario pilot, with a preceding authored control gate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'audit/v2'), str(ROOT / 'audit')]
import audit_v2_scenario_alignment_v2 as previous
import scenario_suite as suite
import scenario_suite_controls as authored

controls, replay = previous.controls, previous.replay
CONFIG = ROOT / 'audit/v2/scenario_suite.v1.json'
TEST = ROOT / 'tests/unit/test_v2_scenario_suite.py'
DOC = ROOT / 'audit/v2/SCENARIO_SUITE.md'
IMPLEMENTATION = [CONFIG, TEST, DOC, Path(__file__).resolve(), Path(suite.__file__), Path(authored.__file__)]


def prepare():
    design = replay.read_json(CONFIG)
    if design['suite_version'] != suite.VERSION or design['maximum_inference_requests'] != 0: raise ValueError('Suite contract differs')
    lock_path = ROOT / design['freeze_lock']; lock = replay.read_json(lock_path)
    if lock['protocol_version'] != design['protocol_version']: raise ValueError('Freeze version differs')
    previous.previous.verify_named_inputs(ROOT, lock['files'], [p.relative_to(ROOT).as_posix() for p in IMPLEMENTATION])
    parent = ROOT / design['parent_alignment']; old = replay.read_json(parent / 'run.json')
    if old['status'] != 'complete' or old.get('source_inputs_unchanged') is not True: raise ValueError('Completed unchanged alignment audit required')
    hashes = previous.previous.previous.prior.previous.coverage.frozen.parent.verify_hashes(parent, old)
    seal = replay.read_json(parent / 'output_sha256.json'); previous.previous.verify_seal(parent, seal)
    if seal['output_fingerprint'] != design['parent_alignment_output_fingerprint']: raise ValueError('Alignment evidence differs')
    previous.verify_directories(old['directory_inventories'])
    for name, saved in old['completed_cells'].items():
        path = Path(saved['path'])
        if controls.sha256(path) != saved['sha256'] or replay.read_json(path)['id'] != name: raise ValueError('Alignment checkpoint changed')
    source_root = ROOT / design['source_replay']; source_run = replay.read_json(source_root / 'run.json')
    source_seal = replay.read_json(source_root / 'output_sha256.json'); previous.previous.verify_seal(source_root, source_seal)
    if (source_run['status'] != 'complete' or source_run.get('source_inputs_unchanged') is not True or
            source_seal['output_fingerprint'] != design['source_replay_output_fingerprint']): raise ValueError('Completed saved-IR replay evidence differs')
    frozen = replay.read_json(source_root / 'frozen_plan.json')
    if suite.adapter.digest(frozen) != source_run['frozen_plan_sha256']: raise ValueError('Saved replay plan changed')
    row = next(r for r in frozen['rows'] if r['source']['id'] == design['source_cell_id'])
    if row['source']['case'] != design['case'] or row['state'] != 'admitted' or row.get('full_ir_schema_valid') is not True: raise ValueError('Original source is not admitted')
    original = Path(row['source']['artifact'])
    if controls.sha256(original) != row['artifact_sha256']: raise ValueError('Original saved IR changed')
    saved_result = previous.previous.verify_checkpoint(source_run['completed_cells'][row['source']['id']], row)
    if not saved_result['business_suite_pass']: raise ValueError('Previously verified source suite did not pass')
    instance = ROOT / 'benchmark/instances' / design['case']
    runtime_path, assertions_path = instance / 'runtime/manifest.yaml', instance / 'gold/assertions.yaml'
    runtime = suite.metadata.document(runtime_path)
    # Input selection consumes only runtime scenario metadata, not assertions.
    specs = []
    for scenario in runtime['scenarios']:
        root, policy = suite.metadata.fixture_root(instance, scenario)
        specs.append(suite.spec(row, scenario, root, design['selector_parameter']))
    if len(specs) != design['required_reviewed_scenarios'] or len({s['scenario_id'] for s in specs}) != len(specs): raise ValueError('Reviewed scenario roster differs')
    assertions = suite.metadata.document(assertions_path)
    definitions = {s['scenario']: s['assertions'] for s in assertions['scenarios']}
    if set(definitions) != {s['scenario_id'] for s in specs} or len(definitions) != len(assertions['scenarios']): raise ValueError('Assertion scenario identity differs')
    if sum(len(d) for d in definitions.values()) != design['expected_reviewed_predicates']: raise ValueError('Reviewed predicate count differs')
    for rows in definitions.values(): suite.validate_assertions(rows)
    if design['controls']['mutants_per_loader'] != len(authored.MUTANTS): raise ValueError('Control mutant roster differs')
    paths = [*IMPLEMENTATION, lock_path, runtime_path, assertions_path, parent / 'output_sha256.json',
             *[parent / relative for relative in seal['files']], source_root / 'output_sha256.json']
    for value in specs:
        paths += [suite.metadata.bounded.safe(value['fixture_root'], name) for name in value['fixture_inventory']['files']]
        paths.append(Path(value['selected_path']))
    for path in paths:
        key = str(path.resolve()); sha = controls.sha256(path) if path.is_file() else 'MISSING'
        if key in hashes and hashes[key] != sha: raise ValueError('Pinned source changed: ' + key)
        hashes[key] = sha
    return {'design': design, 'row': row, 'specs': specs, 'definitions': definitions, 'hashes': hashes,
            'image': source_run['image'], 'directory_inventories': old['directory_inventories']}


def render(output, run):
    lines = ['# V2 complete reviewed-scenario pilot', '', 'Status: ' + run['status'], '', run['design']['scope'], '',
        'Source cell: ' + run['design']['source_cell_id'], '', '## Authored controls', '',
        '| Loader | Genuine scenarios passed | Mutants rejected | Control gate |', '|---|---:|---:|---|']
    for c in run['control_results']:
        lines.append(f"| {c['control_service']} | {c['passed_scenarios']}/{c['required_scenarios']} | {sum(c['mutants'].values())}/{len(c['mutants'])} | {c['control_gate_pass']} |")
    lines += ['', '## Saved IR reviewed scenarios', '', '| Scenario | Snapshot verified | Reviewed predicates passed | Business checks pass | Combined pass |', '|---|---|---:|---|---|']
    for r in run['scenario_results']:
        lines.append(f"| {r['scenario_id']} | {r['snapshot_verified']} | {sum(a['pass'] for a in r['assertions'])}/{len(r['assertions'])} | {bool(r['business_checks']) and all(r['business_checks'].values())} | {r['pass']} |")
    if run.get('suite_summary') is not None:
        lines += ['', 'Suite coverage and result:', '', '```json', __import__('json').dumps(run['suite_summary'], indent=2), '```']
    if run.get('error'): lines += ['', 'Error: ' + run['error']]
    lines += ['', 'Outputs were sealed before predicate evaluation. Inspect each output_snapshot, snapshot_manifest.json, supplied inputs, source hashes, task receipts, database snapshots and SQL dumps.',
        'This is a new single-cell development condition with explicit runtime/input interventions. No original paper score, full Argo/M5 agent result or corpus success rate is replaced.',
        'Private scenario and predicate metadata remain evaluator-only. No LLM or generated program was run.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--dry-run', action='store_true'); args = parser.parse_args(argv)
    print('Verifying source evidence, complete reviewed scenario inputs and the new suite freeze...', flush=True)
    p = prepare(); d = p['design']
    if args.dry_run:
        print(__import__('json').dumps({'source_cell': d['source_cell_id'], 'reviewed_scenarios': [s['scenario_id'] for s in p['specs']],
            'reviewed_predicates': sum(len(x) for x in p['definitions'].values()), 'authored_control_scenarios': 6,
            'authored_mutants': 16, 'verified_input_pins': len(p['hashes']), 'llm_calls': 0, 'runtime_executions': 0}, indent=2)); return 0
    image = suite.transport.image_info(p['image']['id'])
    output = ROOT / 'audit/evaluator_only' / ('package_v2_reviewed_scenarios__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    run = {'status': 'prepared', 'design': d, 'image': image, 'input_fingerprint': controls.fingerprint(p['hashes']),
           'control_results': [], 'scenario_results': [], 'suite_summary': None, 'llm_calls': 0,
           'original_generated_program_executions': 0, 'saved_ir_projection_scenarios': 0, 'evidence_role': 'evaluator_only_never_model_context'}
    controls.write_json(output / 'input_sha256.json', p['hashes']); controls.write_json(output / 'run.json', run)
    controls.write_json(output / 'frozen_scenario_specs.json', p['specs']); controls.write_json(output / 'unchanged_reviewed_predicates.json', p['definitions'])
    for path in [*IMPLEMENTATION, ROOT / d['freeze_lock']]:
        destination = output / 'implementation' / path.relative_to(ROOT); destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, destination)
    print('Output: ' + str(output), flush=True)
    try:
        env = dict(__import__('os').environ); env['P2SF_POSTGRES_TEST_IMAGE'] = image['id']
        tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TEST)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
        if tests.returncode: raise ValueError('Scenario handoff/snapshot verification failed')
        for service in d['controls']['loader_services']:
            result = authored.run(output / 'controls' / service, service, p['row']['plan']['schemas'], image)
            run['control_results'].append(result); controls.write_json(output / 'run.json', run)
            print('authored ' + service + ': control_gate=' + str(result['control_gate_pass']), flush=True)
        gate = len(run['control_results']) == len(d['controls']['loader_services']) and all(c['control_gate_pass'] for c in run['control_results'])
        if gate:
            original = Path(p['row']['source']['artifact']); raw = original.read_bytes()
            if suite.metadata.sha(original) != p['row']['artifact_sha256']: raise ValueError('Source IR changed before execution')
            (output / 'original_saved_ir.yaml').write_bytes(raw)
            for value in p['specs']:
                directory = output / 'scenarios' / value['scenario_id']; suite.execute(p['row'], value, directory, image)
                run['saved_ir_projection_scenarios'] += 1
                result = suite.score(directory, value, p['definitions'][value['scenario_id']]); suite.write(directory / 'score.json', result)
                run['scenario_results'].append(result); controls.write_json(output / 'run.json', run)
                print(value['scenario_id'] + ': pass=' + str(result['pass']), flush=True)
            run['suite_summary'] = suite.aggregate(p['specs'], run['scenario_results'])
            run['status'] = 'complete' if run['suite_summary']['suite_pass'] else 'complete_suite_failed'
        else: run['status'] = 'control_gate_failed_no_saved_replay'
        previous.previous.previous.prior.previous.coverage.frozen.parent.verify_hashes(output, run)
        previous.verify_directories(p['directory_inventories']); run['source_inputs_unchanged'] = True
    except BaseException as exc:
        run['status'] = 'interrupted_or_infrastructure_error'; run['error'] = type(exc).__name__ + ': ' + str(exc)[:1500]
        controls.write_json(output / 'run.json', run); render(output, run); previous.seal_output(output); raise
    controls.write_json(output / 'run.json', run); render(output, run); previous.seal_output(output)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
