#!/usr/bin/env python3
"""Clarified public window semantics: original-IR controls then saved-IR replay.

No private assertions/native reference programs, model calls, or binding repair.
Passing the clarified profile is not a replacement for published G6-Assert.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timedelta, timezone
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
import plan_v2_corpus_replay as planner
import bounded_window_executor as engine
import bounded_window_ops as ops
import bounded_window_oracle as oracle

controls, replay, parent = planner.controls, planner.replay, planner.parent
CONFIG = ROOT / 'audit/v2/bounded_window_profile.json'
TESTS = ROOT / 'tests/unit/test_v2_bounded_window.py'
FILES = list(dict.fromkeys([Path(__file__).resolve(), CONFIG, TESTS,
    ROOT / 'audit/v2/bounded_window_ops.py', ROOT / 'audit/v2/bounded_window_executor.py',
    ROOT / 'audit/v2/bounded_window_oracle.py', ROOT / 'audit/v2/BOUNDED_WINDOW_SPEC.md',
    ROOT / 'scripts/plan_v2_corpus_replay.py', *planner.FILES]))


def prepare_scenarios(active, target, profile):
    config = replay.read_json(active / 'fixture.json')
    source = ops.contained(active, config['inputs'][profile['input_keys']['records']])
    rows = [json.loads(s) for s in source.read_text().splitlines() if s.strip()]
    if not rows:
        raise ValueError('Diagnostic perturbations require at least one public input record')
    fields = profile['fields']
    for name in profile['scenarios']:
        destination = target / 'scenarios' / name
        shutil.copytree(active, destination)
        data = copy.deepcopy(rows)
        if name == 'shuffled':
            data.reverse()
        elif name == 'duplicate':
            data.append(copy.deepcopy(data[0]))
        elif name == 'extra_record':
            row = copy.deepcopy(data[0]); row[fields['entity']] += '__added'; data.append(row)
        elif name == 'changed_energy':
            data[0][fields['energy']] += 7
        elif name == 'boundary_records':
            for suffix, stamp in [('at_end', config['batch_window_end']), ('at_start', config['batch_window_start']),
                                  ('before_start', oracle.z(oracle.time(config['batch_window_start']) - timedelta(microseconds=1)))]:
                row = copy.deepcopy(rows[0]); row[fields['entity']] += '__' + suffix; row[fields['time']] = stamp; data.append(row)
        elif name == 'conflicting_duplicate':
            row = copy.deepcopy(data[0]); row[fields['energy']] += 1; data.append(row)
        elif name == 'unknown_building':
            data[0][fields['group']] = '__unregistered'
        elif name == 'missing_energy':
            del data[0][fields['energy']]
        elif name != 'nominal':
            raise ValueError('Unknown declared scenario')
        output = ops.contained(destination, config['inputs'][profile['input_keys']['records']])
        output.write_text(''.join(json.dumps(r) + '\n' for r in data))


def install(ir, profile, root, fixtures, scenarios):
    scripts = root / 'runtime/scripts'
    scripts.mkdir(parents=True)
    for path in [ROOT / 'audit/v2/bounded_window_ops.py', ROOT / 'audit/v2/bounded_window_executor.py',
                 ROOT / 'audit/retention_adapter.py']:
        shutil.copy2(path, scripts / path.name)
    controls.write_json(scripts / 'ir.json', ir)
    controls.write_json(scripts / 'profile.json', profile)
    (scripts / 'workflow.py').write_text(
        'import argparse,json\nfrom pathlib import Path\nfrom bounded_window_executor import execute\n'
        'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path)\n'
        'a=p.parse_args();root=Path(__file__).parent\n'
        'r=execute(json.loads((root/"ir.json").read_text()),json.loads((root/"profile.json").read_text()),a.workspace,a.fixtures)\n'
        'print(json.dumps(r));raise SystemExit(0 if r["workflow_status"]=="completed" else 2)\n')
    shutil.copytree(fixtures, root / 'fixtures')
    manifest = {'runtime_manifest_version': '0.1.0', 'pipeline_id': 'v2_bounded_original_ir', 'image': 'python:3.12-slim',
        'workflow_parameters': [], 'tasks': [{'intent_id': 'bounded_workflow', 'script': 'scripts/workflow.py',
            'arguments': ['--workspace', '{workspace}', '--fixtures', '{fixtures}'], 'retries': 0}],
        'scenarios': [{'name': n, 'parameters': {}, 'fixture_root': 'fixtures/scenarios/' + n} for n in scenarios]}
    (root / 'runtime/manifest.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def schemas_for(ir, workspace):
    schemas = {}
    for artifact in ir['artifacts']:
        if not artifact.get('schema_ref'):
            continue
        path = ops.contained(workspace, artifact['schema_ref'])
        schema = controls.load(path)
        if any(isinstance(node, dict) and ('$ref' in node or '$dynamicRef' in node) for node in planner.analysis.walk(schema)):
            raise ops.Unsupported('Public schema reference resolution is outside this profile')
        schemas[artifact['artifact_id']] = schema
    return schemas


def run_ir(ir, profile, workspace, scenario_fixtures, output):
    engine.compile_ir(ir)
    schemas = schemas_for(ir, workspace)
    manifest = install(ir, profile, output / 'instance', scenario_fixtures, profile['scenarios'])
    results = controls._execute_scenarios(output / 'instance', manifest, sandbox_generated=True)
    index = controls.persist_snapshots(results, output / 'execution')
    evaluations = {r['scenario']: oracle.check(r, ir, scenario_fixtures / 'scenarios' / r['scenario'], profile, r['scenario'], schemas)
                   for r in results}
    return {'state': 'evaluated_under_clarified_profile', 'scenarios': evaluations, 'execution': index,
            'profile_all_scenarios_pass': len(evaluations) == len(profile['scenarios']) and all(v['pass'] for v in evaluations.values()),
            'original_g6_assert': 'not_measured', 'original_public_gates': 'not_measured'}, results


def negative_controls(nominal, ir, fixtures, profile, output):
    publisher = next(b for b in ir['bindings'] if b['service_id'] == oracle.PUBLISHER)
    identity = next(o['artifact_id'] for o in publisher['output_bindings'] if o['port'] == 'output_artifacts')
    payload_path = 'artifacts/' + identity + '.json'
    checks = {}
    for name in profile['negative_controls']:
        mutant = copy.deepcopy(nominal)
        payload = json.loads(mutant['_snapshot'][payload_path])
        csv_path, audit_path = payload['published_files']['csv'], payload['published_files']['audit']
        raw_rows = list(csv.DictReader(io.StringIO(mutant['_snapshot'][csv_path].decode())))
        header = list(raw_rows[0]) if raw_rows else list(payload['metrics'][0])
        if name == 'constant_summary':
            payload['metrics'] = []; raw_rows = []
        elif name == 'wrong_energy':
            payload['metrics'][0]['energy_kwh_sum'] += 1
            raw_rows[0]['energy_kwh_sum'] = str(float(raw_rows[0]['energy_kwh_sum']) + 1)
        elif name == 'wrong_alert':
            payload['metrics'][0]['high_demand'] = not payload['metrics'][0]['high_demand']
            raw_rows[0]['high_demand'] = str(payload['metrics'][0]['high_demand'])
        elif name == 'missing_publication':
            del mutant['_snapshot'][csv_path]
        else:
            raise ValueError('Unknown negative control')
        if name != 'missing_publication':
            stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=header, lineterminator='\n')
            writer.writeheader(); writer.writerows(raw_rows)
            encoded = stream.getvalue().encode()
            mutant['_snapshot'][csv_path] = encoded
            audit = json.loads(mutant['_snapshot'][audit_path]); audit['csv_sha256'] = hashlib.sha256(encoded).hexdigest()
            mutant['_snapshot'][audit_path] = json.dumps(audit).encode()
        mutant['_snapshot'][payload_path] = json.dumps(payload).encode()
        controls.persist_snapshots([mutant], output / name)
        evaluation = oracle.check(mutant, ir, fixtures, profile, 'nominal')
        checks[name] = {'detected': not evaluation['pass'], 'evaluation': evaluation}
    return checks


def render(run):
    lines = ['# Clarified v2 bounded-window original-IR controls and replay', '',
             f"Package {run['package_version']}; audit protocol {run['audit_protocol_version']}; state {run['status']}; LLM calls 0.",
             'New public-profile semantics. Not published G6-Assert scores or a full public-gate pass.', '']
    reference = run.get('reference', {})
    lines += [f"Reference scenario checks passed: {sum(v['pass'] for v in reference.get('scenarios', {}).values())}/{len(run['profile']['scenarios'])}.",
              f"Reference negative controls detected: {sum(v['detected'] for v in reference.get('negative_controls', {}).values())}/{len(run['profile']['negative_controls'])}.", '',
              f"Original case cells retained: {len(run['cells'])}; M3–M5 replay records: {len(run['models'])}; direct-Argo cells not executed: {sum(c['source']['route']=='direct_argo' for c in run['cells'])}.", '',
              '| Model | Method | Sample | State | Profile scenario checks passed |', '|---|---|---:|---|---:|']
    for source_id, record in run['models'].items():
        source = next(c['source'] for c in run['cells'] if c['source']['id'] == source_id)
        lines.append(f"| {source['model']} | {source['method']} | {source['sample_index']} | {record['state']} | {sum(v['pass'] for v in record.get('scenarios', {}).values())}/{len(run['profile']['scenarios'])} |")
    lines += ['', 'No missing binding, field alias, service choice, parameter, or output was repaired.',
              'The clarified interval-energy/window/aggregation rules are new v2 assumptions; comparisons to old private assertions remain separate.', '']
    return '\n'.join(lines)


def preconditions(profile):
    root = ROOT / profile['parent_coverage']
    previous = replay.read_json(root / 'run.json')
    if previous['status'] not in ('complete', 'complete_with_errors') or not previous['source_inputs_unchanged']:
        raise ValueError('Coverage parent is incomplete or changed')
    if previous['environment'] != controls.environment():
        raise ValueError('Environment differs from verified controls')
    hashes = parent.verify_hashes(root, previous)
    cells = replay.read_json(root / 'saved_cell_coverage.json')
    failures = {c['source']['id'] for c in cells if c['analysis']['state'] in ('inspection_error', 'planner_error')}
    if failures - set(profile['allowed_parent_inspection_errors']):
        raise ValueError('Unreviewed parent inspection errors')
    references = replay.read_json(root / 'pipeline_coverage.json')
    if any(r['analysis']['state'] != 'analyzed' for r in references):
        raise ValueError('Parent reference-side planning has unresolved errors')
    selected = [c for c in cells if c['source']['case'] == profile['case']]
    if len(selected) != 54 or sum(c['source']['route'] == 'serviceflow_ir' for c in selected) != 27:
        raise ValueError('Expected all 54 original cells, including 27 IR cells, for this case')
    # Obtain the original public workspace location from the fixed v3 inventory,
    # not from any model-supplied path or a reconstructed private fixture.
    model_parent = replay.read_json(ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json')
    baseline = Path(model_parent['control_directory'])
    workspace = baseline / 'cases' / profile['case'] / 'public_workspace' / profile['case']
    return root, hashes, selected, workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true'); parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    profile = replay.read_json(CONFIG); ops.verify_profile(profile)
    print('Checking unchanged parent evidence and the fixed original-case roster...', flush=True)
    parent_root, hashes, cells, workspace = preconditions(profile)
    if args.dry_run:
        print(json.dumps({'package_version': profile['package_version'], 'case': profile['case'],
            'reference_scenarios': len(profile['scenarios']), 'negative_controls': len(profile['negative_controls']),
            'original_cells': len(cells), 'ir_cells': 27, 'llm_calls': 0, 'published_scores_replaced': False}, indent=2)); return 0
    extra = [*FILES, parent_root / 'run.json', parent_root / 'input_sha256.json', parent_root / 'saved_cell_coverage.json', parent_root / 'pipeline_coverage.json']
    hashes.update({str(p.resolve()): controls.sha256(p) for p in extra})
    fingerprint = controls.fingerprint(hashes)
    if args.resume:
        output = args.resume.resolve(); run = replay.read_json(output / 'run.json')
        if run['input_fingerprint'] != fingerprint or run['cells'] != cells:
            raise ValueError('Bounded-window inputs/profile/code changed; start a new condition')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_bounded_window__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': profile['package_version'], 'audit_protocol_version': profile['audit_protocol_version'],
            'profile': profile, 'input_fingerprint': fingerprint, 'environment': controls.environment(),
            'llm_calls': 0, 'cells': cells, 'models': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        for path in FILES:
            target = output / 'implementation' / path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    run['status'] = 'running'; controls.write_json(output / 'run.json', run); print(f'Output: {output}', flush=True)
    verification = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(verification.stdout + verification.stderr)
    if verification.returncode:
        run['status'] = 'verification_failed'; controls.write_json(output / 'run.json', run); raise ValueError('Bounded-window tests failed')
    if not run.get('scenario_inputs'):
        fixture_root = output / ('scenario_inputs_' + uuid.uuid4().hex[:8])
        prepare_scenarios(workspace / 'fixtures/scenarios/nominal', fixture_root, profile)
        run['scenario_inputs'] = str(fixture_root)
        run['scenario_input_sha256'] = {p.relative_to(fixture_root).as_posix(): controls.sha256(p) for p in fixture_root.rglob('*') if p.is_file()}
        controls.write_json(output / 'run.json', run)
    fixtures = Path(run['scenario_inputs'])
    if run['scenario_input_sha256'] != {p.relative_to(fixtures).as_posix(): controls.sha256(p) for p in fixtures.rglob('*') if p.is_file()}:
        raise ValueError('Derived scenario inputs changed; do not resume this condition')
    reference_ir = controls.BENCHMARK / 'instances' / profile['case'] / 'gold/serviceflow.yaml'
    if 'reference' not in run:
        attempt = output / 'reference' / ('attempt_' + uuid.uuid4().hex[:8])
        try:
            ir = controls.load(reference_ir)
            record, raw = run_ir(ir, profile, workspace, fixtures, attempt)
            negatives = (negative_controls(next(r for r in raw if r['scenario'] == 'nominal'), ir, fixtures / 'scenarios/nominal', profile, attempt / 'negative_controls')
                         if record['scenarios']['nominal']['pass'] else {})
            record['negative_controls'] = negatives
        except Exception as exc:
            record = {'state': 'reference_error', 'profile_all_scenarios_pass': False, 'error': f'{type(exc).__name__}: {exc}'}
        record['artifact_directory'] = str(attempt)
        run['reference'] = record; controls.write_json(output / 'run.json', run)
    gate = (run['reference']['profile_all_scenarios_pass']
            and set(run['reference'].get('negative_controls', {})) == set(profile['negative_controls'])
            and all(n['detected'] for n in run['reference']['negative_controls'].values()))
    if not gate:
        run['status'] = 'reference_controls_failed'; controls.write_json(output / 'run.json', run)
        (output / 'summary.md').write_text(render(run)); print(f"reference_controls_failed: {output / 'summary.md'}", flush=True); return 1
    for cell in cells:
        source = cell['source']
        if source['route'] != 'serviceflow_ir' or source['id'] in run['models']:
            continue
        path = Path(source['artifact']); attempt = output / 'models' / ('attempt_' + uuid.uuid4().hex[:8])
        try:
            if not path.is_file():
                record = {'state': 'missing_saved_ir'}
            else:
                ir = controls.load(path)
                record, _ = run_ir(ir, profile, workspace, fixtures, attempt)
                record['source_ir_sha256'] = controls.sha256(path)
        except ops.Unsupported as exc:
            record = {'state': 'unsupported_profile_or_binding', 'reason': str(exc)}
        except (ValueError, KeyError, TypeError, OSError, controls.yaml.YAMLError) as exc:
            record = {'state': 'invalid_or_unavailable_saved_input', 'reason': f'{type(exc).__name__}: {exc}'}
        except Exception as exc:
            record = {'state': 'runner_error', 'reason': f'{type(exc).__name__}: {exc}'}
        record['artifact_directory'] = str(attempt); controls.write_json(attempt / 'result.json', record)
        run['models'][source['id']] = record; controls.write_json(output / 'run.json', run)
        (output / 'summary.md').write_text(render(run)); print(source['id'] + ': ' + record['state'], flush=True)
    try:
        parent.verify_hashes(output, run)
        unchanged = run['scenario_input_sha256'] == {p.relative_to(fixtures).as_posix(): controls.sha256(p) for p in fixtures.rglob('*') if p.is_file()}
    except ValueError as exc:
        unchanged = False; run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if any(r['state'] == 'runner_error' for r in run['models'].values()) else 'complete'
    controls.write_json(output / 'run.json', run); (output / 'summary.md').write_text(render(run))
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
