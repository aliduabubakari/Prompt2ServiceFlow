#!/usr/bin/env python3
"""Business-output controls for mock vs existing real-profile execution."""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_output_trace as trace
import run_v2_paired_window as real

generation = trace.generation
controls, replay, parent = trace.controls, trace.replay, trace.parent
CONFIG = ROOT / 'audit/v2/backend_controls.json'
TESTS = ROOT / 'tests/unit/test_v2_backend_controls.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/BACKEND_CONTROLS.md',
         ROOT / 'audit/v2/bounded_window_oracle.py', ROOT / 'audit/v2/BOUNDED_WINDOW_SPEC.md']


def restored(entry, execution):
    directory = trace.local(execution, entry['directory'])
    snapshot = {}
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual != set(entry['artifact_sha256']):
        raise ValueError('Cached snapshot inventory changed')
    for relative, digest in entry['artifact_sha256'].items():
        path = trace.local(directory, relative)
        if controls.sha256(path) != digest:
            raise ValueError('Cached real output changed')
        snapshot[relative] = path.read_bytes()
    return {'scenario': entry['scenario'], '_snapshot': snapshot, '_errors': entry['execution_errors']}


def neutral_check(result, ir, fixtures, profile):
    """Public numerical/CSV contract only; no engine trace or gold assertions."""
    checks = []
    def add(name, passed): checks.append({'check': name, 'pass': bool(passed)})
    try:
        snapshot = result['_snapshot']
        add('no_execution_error', not result['_errors'])
        identity = real.oracle.primary(ir)
        payload = json.loads(snapshot['artifacts/' + identity + '.json'])
        expected, counts = real.oracle.base.expected(fixtures, profile)
        add('metrics_from_public_inputs', real.oracle.base.equivalent(payload['metrics'], expected))
        add('input_duplicate_window_counts', payload['counts'] == counts)
        paths = payload['published_files']
        for path in (paths['csv'], paths['audit']):
            if not isinstance(path, str) or not path.startswith('published/') or '..' in Path(path).parts:
                raise ValueError('Unsafe business output path')
        raw = snapshot[paths['csv']]
        parsed = list(csv.DictReader(io.StringIO(raw.decode())))
        for row in parsed:
            row['record_count'] = int(row['record_count'])
            for field in ('energy_kwh_sum', 'peak_demand_kw', 'mean_power_factor', 'demand_pct'):
                row[field] = float(row[field])
            for field in ('high_demand', 'low_power_factor'):
                if row[field] not in ('True', 'False'):
                    raise ValueError('CSV alerts must be Boolean values')
                row[field] = row[field] == 'True'
        add('published_csv_from_public_inputs', real.oracle.base.equivalent(parsed, expected))
        audit = json.loads(snapshot[paths['audit']])
        add('audit_counts_and_actual_csv_hash', audit['counts'] == counts and audit['csv_sha256'] == hashlib.sha256(raw).hexdigest())
        add('declared_profile_hash', audit['profile_sha256'] == controls.fingerprint(profile))
        config = replay.read_json(fixtures / 'fixture.json')
        source_hashes = {name: controls.sha256(real.oracle.base.source_path(fixtures, config['inputs'][profile['input_keys'][name]]))
                         for name in ('records', 'registry')}
        add('actual_source_hashes', audit['source_sha256'] == source_hashes)
    except Exception as exc:
        checks.append({'check': 'business_output_unavailable_or_invalid', 'pass': False,
                       'error': type(exc).__name__ + ': ' + str(exc)})
    return {'pass': bool(checks) and all(c['pass'] for c in checks), 'checks': checks,
            'scope': 'explicit_v2_public_profile_business_control_not_original_g6'}


def mutate(result, ir, condition):
    result = copy.deepcopy(result)
    snapshot = result['_snapshot']
    payload_path = 'artifacts/' + real.oracle.primary(ir) + '.json'
    payload = json.loads(snapshot[payload_path])
    csv_path, audit_path = payload['published_files']['csv'], payload['published_files']['audit']
    if condition == 'missing_publication':
        del snapshot[csv_path]
        return result
    rows = list(csv.DictReader(io.StringIO(snapshot[csv_path].decode())))
    columns = list(rows[0])
    if condition == 'constant_summary':
        payload['metrics'], rows = [], []
    elif condition == 'wrong_energy':
        payload['metrics'][0]['energy_kwh_sum'] += 1
        rows[0]['energy_kwh_sum'] = str(float(rows[0]['energy_kwh_sum']) + 1)
    elif condition == 'wrong_alert':
        payload['metrics'][0]['high_demand'] = not payload['metrics'][0]['high_demand']
        rows[0]['high_demand'] = str(payload['metrics'][0]['high_demand'])
    else:
        raise ValueError('Unknown fixed negative control')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    raw = stream.getvalue().encode()
    snapshot[csv_path] = raw
    audit = json.loads(snapshot[audit_path])
    audit['csv_sha256'] = hashlib.sha256(raw).hexdigest()
    snapshot[audit_path] = json.dumps(audit).encode()
    snapshot[payload_path] = json.dumps(payload).encode()
    return result


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference allowed')
    trace_root = ROOT / design['parent_trace']
    previous = replay.read_json(trace_root / 'run.json')
    if previous['status'] != 'complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged static trace required')
    hashes = parent.verify_hashes(trace_root, previous)
    generation.verify_completed(previous)
    real_root = ROOT / design['parent_real_controls']
    cached = replay.read_json(real_root / 'run.json')
    if cached['status'] != 'complete' or cached.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged real-profile controls required')
    old_pins = parent.verify_hashes(real_root, cached)
    if any(k in hashes and hashes[k] != v for k, v in old_pins.items()):
        raise ValueError('Parent evidence conflicts')
    hashes.update(old_pins)
    control = cached['controls'][design['reference_control']]
    if not real.control_pass(control, design['reference_control']):
        raise ValueError('Real backend scenario/mutation controls must already pass')
    attempt = Path(control['artifact_directory'])
    ir_path = attempt / 'effective_ir.yaml'
    if controls.sha256(ir_path) != control['effective_ir_sha256']:
        raise ValueError('Verified reference control IR changed')
    profile = cached['profile']
    if set(design['positive_scenarios']) - set(profile['scenarios']):
        raise ValueError('Unknown public positive scenario')
    fixtures = attempt / 'instance/fixtures'
    execution = attempt / 'execution'
    entries = replay.read_json(execution / 'index.json')
    if entries != control['execution'] or len({e['scenario'] for e in entries}) != len(entries):
        raise ValueError('Cached execution index changed')
    selected = {e['scenario']: e for e in entries if e['scenario'] in design['positive_scenarios']}
    if set(selected) != set(design['positive_scenarios']):
        raise ValueError('Missing original positive scenario snapshots')
    snapshots = {name: restored(entry, execution) for name, entry in selected.items()}
    inventory = replay.read_json(ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json')
    workspace = Path(inventory['control_directory']) / 'cases' / profile['case'] / 'public_workspace' / profile['case']
    generation.census.public_context(workspace)
    paths = [*FILES, trace_root / 'run.json', trace_root / 'input_sha256.json', real_root / 'run.json',
             real_root / 'input_sha256.json', ir_path, execution / 'index.json']
    for saved in previous['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    paths.extend(p for p in workspace.rglob('*') if p.is_file())
    paths.extend(p for p in fixtures.rglob('*') if p.is_file())
    for entry in entries:
        paths.extend(trace.local(execution, entry['directory']) / name for name in entry['artifact_sha256'])
    for path in paths:
        name, digest = str(path.resolve()), controls.sha256(path)
        if name in hashes and hashes[name] != digest:
            raise ValueError('Pinned control source changed')
        hashes[name] = digest
    return design, controls.load(ir_path), profile, workspace, fixtures, snapshots, hashes


def install_mock(ir, profile, workspace, fixtures, directory, scenarios):
    if directory.exists():
        raise ValueError('New isolated control directory required')
    shutil.copytree(workspace, directory)
    shutil.rmtree(directory / 'fixtures')
    shutil.copytree(fixtures, directory / 'fixtures')
    # Only this fresh control copy is compiled. No saved model/reference
    # submission or benchmark workspace is modified.
    (directory / 'serviceflow.yaml').write_text(controls.yaml.safe_dump(ir, sort_keys=False))
    controls.write_json(directory / 'public_v2_profile.json', profile)
    if (directory / 'runtime').exists():
        raise ValueError('Public workspace unexpectedly contains a runtime')
    trace.runtime_compiler.materialize_runtime(directory, directory, replace=False)
    manifest = controls.load(directory / 'runtime/manifest.yaml')
    manifest['scenarios'] = [s for s in manifest['scenarios'] if s['name'] in scenarios]
    if {s['name'] for s in manifest['scenarios']} != set(scenarios):
        raise ValueError('Frozen compiler scenario roster mismatch')
    (directory / 'runtime/manifest.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def render(run):
    lines = ['# Reference backend business-output controls', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}.",
        'Same reference IR and six public input variants; frozen mock execution versus verified cached real-profile outputs.',
        'New explicit v2 operation interpretation; not original model scores or original G6-Assert.', '',
        '| Scenario | Frozen mock business checks | Cached real-profile business checks |', '|---|---|---|']
    for scenario in run['design']['positive_scenarios']:
        a = run['results']['frozen_mock_execution'][scenario]['pass']
        b = run['results']['cached_real_profile_execution'][scenario]['pass']
        lines.append(f'| {scenario} | {a} | {b} |')
    lines += ['', '## Independent checker negative controls', '']
    lines.extend(f"- {name}: detected={value['detected']}" for name, value in run['negative_controls'].items())
    lines += ['', 'Checks use business metrics, CSV values, counts and publication integrity, not backend-specific internal traces.',
        'No model call occurs. Only frozen generated reference scripts are newly executed, in the network-disabled sandbox.',
        'Real outputs are checksum-verified cached controls. No model-generated workflow is rerun or patched.',
        'This comparison includes the declared v2 operation profile; it is not proof of equivalence to undocumented v1 operation labels.',
        'A reference control pass is not a model accuracy estimate or corpus-wide semantic result. Other service families remain unsupported until implemented and controlled.',
        'Original v1, scores, submitted paper, deposit, and prior audit evidence remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying mock trace, real-profile controls and cached business outputs...', flush=True)
    design, ir, profile, workspace, fixtures, snapshots, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'case': profile['case'], 'new_mock_scenario_executions': len(design['positive_scenarios']),
                          'cached_real_scenarios': len(snapshots), 'negative_controls': len(design['negative_controls']),
                          'verified_inputs': len(hashes), 'api_requests': 0, 'original_model_workflows_executed': 0,
                          'original_scores_replaced': False}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/outputs' / f'package_v2_backend_controls__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
           'status': 'running', 'results': {}, 'result_files': {}}
    controls.write_json(output / 'run.json', run)
    controls.write_json(output / 'input_sha256.json', hashes)
    for path in FILES:
        target = output / 'implementation' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        print('verification_failed: ' + str(output / 'verification.txt'), flush=True)
        return 1
    parent.verify_hashes(output, run)
    real_checks = {name: neutral_check(result, ir, fixtures / 'scenarios' / name, profile) for name, result in snapshots.items()}
    negatives = {}
    for condition in design['negative_controls']:
        mutant = mutate(snapshots['nominal'], ir, condition)
        checked = neutral_check(mutant, ir, fixtures / 'scenarios/nominal', profile)
        negatives[condition] = {'detected': not checked['pass'], 'evaluation': checked}
    run['results']['cached_real_profile_execution'] = real_checks
    run['negative_controls'] = negatives
    # Validate the checker against previously verified outputs before any
    # sandbox execution. Do not tune it to the observed mock outcomes.
    if not all(v['pass'] for v in real_checks.values()) or not all(v['detected'] for v in negatives.values()):
        run['status'] = 'checker_control_failed'
        controls.write_json(output / 'run.json', run)
        print('checker_control_failed: ' + str(output / 'run.json'), flush=True)
        return 1
    manifest = install_mock(ir, profile, workspace, fixtures, output / 'mock_instance', design['positive_scenarios'])
    results = controls._execute_scenarios(output / 'mock_instance', manifest, sandbox_generated=True)
    controls.persist_snapshots(results, output / 'mock_execution')
    run['results']['frozen_mock_execution'] = {r['scenario']: neutral_check(r, ir, fixtures / 'scenarios' / r['scenario'], profile) for r in results}
    if set(run['results']['frozen_mock_execution']) != set(design['positive_scenarios']):
        raise ValueError('Do not publish a partial mock/control comparison')
    evidence = output / 'evidence'
    controls.write_json(evidence / 'result.json', {'results': run['results'], 'negative_controls': negatives})
    run['result_files']['backend_controls'] = generation.output_checkpoint(evidence)
    run['execution_file_sha256'] = {p.relative_to(output).as_posix(): controls.sha256(p)
                                   for p in (output / 'mock_execution').rglob('*') if p.is_file()}
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    execution_error = any(r['_errors'] for r in results)
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if execution_error else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
