#!/usr/bin/env python3
"""Frozen, resumable replay of saved IR; unsupported cells remain in coverage."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_resolution as resolution

pilot, generation = resolution.pilot, resolution.generation
controls, replay, parent = resolution.controls, resolution.replay, resolution.parent
census = generation.census
CONFIG = ROOT / 'audit/v2/semantic_replay.json'
FREEZE = ROOT / 'audit/v2/freeze.semantic-replay.v2.json'
TESTS = ROOT / 'tests/unit/test_v2_frozen_semantic_replay.py'
DOC = ROOT / 'audit/v2/FROZEN_SEMANTIC_REPLAY.md'


def local_implementations():
    files = {Path(__file__).resolve(), CONFIG, TESTS, DOC,
             ROOT / 'audit/v2/runtime_profiles/IR_INPUT_OUTPUT_RULES.md'}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if (path.is_relative_to(ROOT) and '.venv' not in path.parts
                    and 'tests' not in path.relative_to(ROOT).parts and path.is_file()):
                files.add(path)
    return sorted(files)


def merged(first, second):
    result = dict(first)
    for name, digest in second.items():
        if name in result and result[name] != digest:
            raise ValueError('Conflicting evidence hashes: ' + name)
        result[name] = digest
    return result


def verified_evidence():
    design = replay.read_json(CONFIG)
    if (design['maximum_inference_requests'] != 0 or design['maximum_workers'] != 1
            or design['conditions'] != ['raw', 'frozen_completion']
            or design['runtime_selection'] != 'reference'
            or design['operation_labels'] != 'exact_registered_labels_only'):
        raise ValueError('Only the declared zero-inference, exact-contract study is implemented')
    root = ROOT / design['validated_resolution']
    validation = replay.read_json(root / 'run.json')
    if (validation['status'] != 'complete' or validation.get('source_inputs_unchanged') is not True
            or validation['outcome'].get('profile_all_controls_pass') is not True
            or validation['outcome'].get('positive_passes') != 6
            or validation['outcome'].get('correct_rejections') != 3):
        raise ValueError('Successful unchanged v2 development execution required')
    hashes = parent.verify_hashes(root, validation)
    generation.verify_completed(validation)
    source_root = ROOT / validation['design']['source_pilot']
    source = replay.read_json(source_root / 'run.json')
    generation.verify_completed(source)
    fixtures = source_root / 'evaluation_fixtures'
    if pilot.file_hashes(fixtures) != source['evaluation_fixture_files']:
        raise ValueError('Validated evaluation fixtures changed')
    profile = replay.read_json(ROOT / design['profile'])
    if profile != source['profile']:
        raise ValueError('Numerical profile differs from validated execution')
    projection = replay.read_json(ROOT / design['projection_contract'])
    resolution.semantic_completion.validate_contract(projection)
    policy = replay.read_json(ROOT / design['assembly_policy'])
    census_root = ROOT / design['parent_census']
    recorded = replay.read_json(census_root / 'run.json')
    if recorded['status'] != 'complete' or recorded.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged full original census required')
    hashes = merged(hashes, parent.verify_hashes(census_root, recorded))
    census.verify_roster(recorded['sources'], recorded['cases'], recorded['design'])
    records = census.read_checkpoints(recorded, recorded['cases'])
    cells = [cell for record in records for cell in record['model_cells']]
    by_id = {row['source']['id']: row for row in cells}
    if (len(by_id) != len(cells) or len(cells) != design['expected_original_cells']
            or sum(r['source']['route'] == 'serviceflow_ir' for r in cells) != design['expected_original_ir_cells']):
        raise ValueError('Original census roster differs')
    cells = [by_id[s['id']] for s in recorded['sources']]
    source_hashes = {}
    for row, source_identity in zip(cells, recorded['sources']):
        if row['source'] != source_identity:
            raise ValueError('Census checkpoint source identity disagrees with roster')
        path = Path(row['source']['artifact'])
        digest = controls.sha256(path) if path.is_file() else 'MISSING'
        if digest != row.get('artifact_sha256', 'MISSING'):
            raise ValueError('Saved artifact availability or contents changed: ' + row['source']['id'])
        source_hashes[str(path.resolve())] = digest
    hashes = merged(hashes, source_hashes)
    inventory = replay.read_json(ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json')
    case = source['design']['case']
    workspace = Path(inventory['control_directory']) / 'cases' / case / 'public_workspace' / case
    context = census.public_context(workspace)
    manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, manifest)
    schema = controls.load(workspace / 'schemas/serviceflow_ir.schema.json')
    # One reviewed public task/profile association. A shared service roster does
    # not establish that other tasks have the same numerical semantics.
    bindings = {case: {'profile_version': profile['profile_version'],
                      'public_task_sha256': controls.sha256(workspace / 'task.md')}}
    paths = [*local_implementations(), CONFIG, root / 'run.json', root / 'input_sha256.json',
             census_root / 'run.json', census_root / 'input_sha256.json', source_root / 'run.json',
             ROOT / design['profile'], ROOT / design['projection_contract'], ROOT / design['assembly_policy']]
    paths.extend(Path(v['path']) for v in recorded['completed_cases'].values())
    paths.extend(fixtures / name for name in source['evaluation_fixture_files'])
    paths.extend(workspace / entry['path'] for entry in manifest['files'])
    hashes = merged(hashes, {str(p.resolve()): controls.sha256(p) for p in paths})
    return {'design': design, 'cells': cells, 'cases': recorded['cases'], 'profile_bindings': bindings,
            'workspace': workspace, 'context': context, 'schema': schema, 'profile': profile,
            'projection': projection, 'policy': policy, 'fixtures': fixtures,
            'scenario_design': source['design'], 'validation': validation, 'hashes': hashes}


def create_freeze():
    """Maintainer preparation only; deliberately absent from the replay CLI."""
    if FREEZE.exists():
        raise ValueError('Freeze exists; create a new version instead of overwriting it')
    prepared = verified_evidence()
    paths = set(local_implementations()) | {ROOT / prepared['design'][key]
                                          for key in ('profile', 'projection_contract', 'assembly_policy')}
    freeze = {'freeze_id': 'p2sf-semantic-replay-v2.1', 'status': 'frozen', 'freeze_format_version': 1,
              'created_at': datetime.now(timezone.utc).isoformat(),
              'design': prepared['design'], 'profile_bindings': prepared['profile_bindings'],
              'files_sha256': {p.relative_to(ROOT).as_posix(): controls.sha256(p) for p in sorted(paths)},
              'evidence_fingerprint': controls.fingerprint(prepared['hashes']),
              'environment': controls.environment(), 'scope': prepared['design']['scope']}
    controls.write_json(FREEZE, freeze)
    return freeze


def verify_freeze(freeze, prepared):
    if (freeze.get('status') != 'frozen' or freeze.get('freeze_format_version') != 1
            or freeze.get('design') != prepared['design']
            or freeze.get('profile_bindings') != prepared['profile_bindings']
            or freeze.get('evidence_fingerprint') != controls.fingerprint(prepared['hashes'])
            or not freeze.get('files_sha256')):
        raise ValueError('Frozen design, source evidence or public profile association changed')
    for name, digest in freeze['files_sha256'].items():
        path = ROOT / name
        if not path.resolve().is_relative_to(ROOT) or controls.sha256(path) != digest:
            raise ValueError('Frozen implementation changed: ' + name)
    if any(p.relative_to(ROOT).as_posix() not in freeze['files_sha256'] for p in local_implementations()):
        raise ValueError('Local implementation dependency missing from freeze')
    current = controls.environment()
    for package in ('PyYAML', 'jsonschema'):
        if current['packages'].get(package) != freeze['environment']['packages'].get(package):
            raise ValueError('Frozen parser/validator dependency changed: ' + package)


def plan_cell(cell, prepared):
    source = cell['source']
    row = {'source': copy.deepcopy(source), 'artifact_sha256': cell.get('artifact_sha256', 'MISSING'),
           'prior_availability_state': cell['analysis']['state'], 'conditions': {}, 'blockers': []}
    if source['route'] == 'direct_argo':
        row['state'] = 'not_applicable_direct_argo'
        return row
    if row['artifact_sha256'] == 'MISSING':
        row['state'] = 'missing_saved_ir'
        return row
    if cell['analysis']['state'] != 'inspected':
        row['state'] = 'unreadable_or_invalid_saved_ir'
        return row
    if source['case'] not in prepared['profile_bindings']:
        row['state'] = 'unsupported_task_profile'
        return row
    try:
        ir = controls.load(Path(source['artifact']))
        if not isinstance(ir, dict):
            raise ValueError('IR must be an object')
        if ir.get('runtime', {}).get('execution_profile') != 'reference':
            row['blockers'].append({'code': 'runtime_selection_not_reference',
                                    'actual': ir.get('runtime', {}).get('execution_profile')})
        operations = pilot.integration.backend.window.OPERATIONS
        for binding in ir.get('bindings', []):
            supported = operations.get(binding.get('service_id'))
            if not supported or binding.get('service_version') != '1.0.0':
                row['blockers'].append({'code': 'unregistered_service_version', 'intent_id': binding.get('intent_id')})
            elif binding.get('parameter_bindings', {}).get('operation_profile') != supported[0]:
                row['blockers'].append({'code': 'operation_label_not_registered', 'intent_id': binding.get('intent_id'),
                    'actual': binding.get('parameter_bindings', {}).get('operation_profile'), 'required': supported[0]})
        split, identity = source['case'].split('/', 1)
        if ir.get('source', {}).get('split') != split or ir.get('source', {}).get('pipeline_id') != identity:
            row['blockers'].append({'code': 'saved_source_identity_mismatch'})
        if row['blockers']:
            row['state'] = 'incompatible_explicit_execution_contract'
            return row
        catalog = census.Catalog()
        completed, decision = resolution.semantic_completion.complete(ir,
            lambda s, v: catalog.get(prepared['workspace'], s, v), prepared['projection'], prepared['policy'])
        for condition, value, edits in [('raw', ir, {'state': 'not_applied', 'operations': []}),
                                        ('frozen_completion', completed, decision)]:
            inspection = pilot.inspect_candidate(value, prepared['schema'], prepared['workspace'], prepared['context'], prepared['profile'])
            if edits['state'] == 'blocked_no_changes':
                inspection = {**inspection, 'state': 'completion_ambiguous'}
            row['conditions'][condition] = {'state': inspection['state'], 'inspection': inspection,
                                           'candidate_ir': value, 'assembly': edits}
        row['state'] = 'planned'
    except Exception as exc:
        row.update(state='inspection_error', reason=type(exc).__name__ + ': ' + str(exc))
    return row


def plan_summary(rows):
    ir = [r for r in rows if r['source']['route'] == 'serviceflow_ir']
    return {'original_cells': len(rows), 'original_ir_cells': len(ir),
            'direct_argo_cells_not_applicable': len(rows) - len(ir),
            'states': dict(Counter(r['state'] for r in rows)),
            'ready_conditions': dict(Counter(c for r in rows for c, v in r['conditions'].items() if v['state'] == 'ready')),
            'ready_ir_cells': sum(any(v['state'] == 'ready' for v in r['conditions'].values()) for r in ir),
            'blocker_cells': dict(Counter(code for r in ir for code in {b['code'] for b in r['blockers']})),
            'api_requests': 0, 'original_scores_replaced': False}


def run_cell(row, directory, prepared):
    result = copy.deepcopy({k: v for k, v in row.items() if k != 'conditions'})
    result['conditions'] = {}
    for condition, planned in row['conditions'].items():
        if planned['state'] != 'ready':
            result['conditions'][condition] = {'state': planned['state'], 'evaluated': False,
                                              'profile_all_controls_pass': None}
            continue
        raw = row['conditions'].get('raw')
        if (condition == 'frozen_completion' and raw and raw['state'] == 'ready'
                and raw['candidate_ir'] == planned['candidate_ir']):
            result['conditions'][condition] = {**copy.deepcopy(result['conditions']['raw']), 'execution_reused_from': 'raw'}
            continue
        attempt = directory / condition
        outcome = pilot.run_condition(attempt, planned['candidate_ir'], prepared['schema'], prepared['workspace'],
            prepared['context'], prepared['profile'], prepared['fixtures'], prepared['scenario_design'], planned['assembly'])
        result['conditions'][condition] = outcome
    return result


def aggregate(rows):
    groups = {}
    for row in rows:
        source = row['source']
        if source['route'] != 'serviceflow_ir':
            continue
        for condition in ('raw', 'frozen_completion'):
            key = (source['model'], source['method'], condition)
            g = groups.setdefault(key, dict(model=key[0], method=key[1], condition=key[2], declared=0,
                                           evaluated=0, passed=0, not_evaluated=0))
            g['declared'] += 1
            outcome = row['conditions'].get(condition, {})
            evaluated = outcome.get('evaluated') is True
            g['evaluated'] += evaluated
            g['not_evaluated'] += not evaluated
            g['passed'] += evaluated and outcome.get('profile_all_controls_pass') is True
    return [{**g, 'evaluated_pass_rate': g['passed'] / g['evaluated'] if g['evaluated'] else None,
             'coverage': g['evaluated'] / g['declared'],
             'declared_pass_yield': g['passed'] / g['declared']} for _, g in sorted(groups.items())]


def persist_report(output, run, rows, summary):
    controls.write_json(output / 'results.json', rows)
    groups = aggregate(rows)
    controls.write_json(output / 'aggregate.json', {'coverage': summary, 'model_method': groups})
    stream = io.StringIO(newline='')
    fields = ['cell', 'model', 'method', 'case', 'stratum', 'sample', 'route', 'availability', 'state', 'condition', 'evaluated', 'passed', 'reason']
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
    for row in rows:
        s = row['source']
        for condition in ('raw', 'frozen_completion') if s['route'] == 'serviceflow_ir' else ('not_applicable',):
            outcome = row['conditions'].get(condition, {})
            writer.writerow(dict(cell=s['id'], model=s['model'], method=s['method'], case=s['case'], stratum=s['case'].split('/')[0],
                sample=s['sample_index'], route=s['route'], availability=row['prior_availability_state'], state=outcome.get('state', row['state']),
                condition=condition, evaluated=outcome.get('evaluated', False), passed=outcome.get('profile_all_controls_pass'),
                reason=json.dumps(row.get('blockers') or row.get('reason') or [], separators=(',', ':'))))
    (output / 'cells.csv').write_text(stream.getvalue())
    lines = ['# Frozen v2 saved-composition replay', '',
             f"Freeze {run['freeze']['freeze_id']}; status {run['status']}; zero LLM calls.", '',
             f"Original cells retained: {summary['original_cells']}; IR cells: {summary['original_ir_cells']}; direct-Argo cells not applicable: {summary['direct_argo_cells_not_applicable']}.",
             f"IR cells compatible with the explicit contract: {summary['ready_ir_cells']}.", '',
             '| Original cell state | Count |', '|---|---:|']
    lines.extend(f'| {state} | {count} |' for state, count in sorted(summary['states'].items()))
    lines += ['', '| Model | Method | Condition | Declared IR | Evaluated | Passed all cases | Pass rate among evaluated |', '|---|---|---|---:|---:|---:|---:|']
    for g in groups:
        rate = '-' if g['evaluated_pass_rate'] is None else f"{g['evaluated_pass_rate']:.3f}"
        lines.append(f"| {g['model']} | {g['method']} | {g['condition']} | {g['declared']} | {g['evaluated']} | {g['passed']} | {rate} |")
    lines += ['', 'Zero evaluated cells means no semantic-rate estimate. Unsupported and missing outputs remain in coverage; they are not measured semantic failures.',
              'The earlier v2 development composition passed six positive cases and three rejection cases; it is excluded from the original-cell denominator and is not a fresh batch observation.',
              'Original operation labels, runtime choices, services, parameters, inputs and control flow are preserved. No silent mock-to-reference change, label translation, reference replacement or LLM repair is allowed.',
              'The reviewed numerical profile is associated with one public task. Other tasks remain unsupported even if their service rosters resemble it.',
              'See cells.csv, plan.json, results.json, aggregate.json, freeze.json and input_sha256.json. Stratum labels are retained; summaries pool them.',
              'This is exploratory v2 execution and coverage, not replacement paper scores, unchanged G6-Assert, full G0–G5 measurement or Argo deployment.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying frozen implementation, validated execution and original saved outputs (no LLM)...', flush=True)
    prepared = verified_evidence()
    freeze = replay.read_json(FREEZE)
    verify_freeze(freeze, prepared)
    prepared['hashes'] = merged(prepared['hashes'], {str(FREEZE.resolve()): controls.sha256(FREEZE)})
    rows = [plan_cell(cell, prepared) for cell in prepared['cells']]
    summary = plan_summary(rows)
    if args.dry_run:
        print(json.dumps({'freeze': freeze['freeze_id'], **summary}, indent=2))
        return 0
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if (run['freeze'] != freeze or run['plan_fingerprint'] != controls.fingerprint(rows)
                or run['input_fingerprint'] != controls.fingerprint(prepared['hashes'])):
            raise ValueError('Frozen replay inputs, code or plan changed; cannot resume')
        if controls.sha256(output / 'plan.json') != run['plan_sha256']:
            raise ValueError('Saved replay plan changed')
        generation.verify_completed(run)
        if (run['completed_cases'] != run['result_files']
                or set(run['completed_cases']) - set(prepared['cases'])):
            raise ValueError('Case checkpoint roster changed')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_frozen_replay__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': prepared['design']['package_version'], 'audit_protocol_version': prepared['design']['audit_protocol_version'],
               'freeze': freeze, 'input_fingerprint': controls.fingerprint(prepared['hashes']), 'plan_fingerprint': controls.fingerprint(rows),
               'environment': controls.environment(), 'status': 'running', 'completed_cases': {}, 'result_files': {}}
        controls.write_json(output / 'input_sha256.json', prepared['hashes'])
        controls.write_json(output / 'freeze.json', freeze)
        controls.write_json(output / 'plan.json', rows)
        run['plan_sha256'] = controls.sha256(output / 'plan.json')
        controls.write_json(output / 'run.json', run)
        for name in freeze['files_sha256']:
            target = output / 'implementation' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS), str(resolution.TESTS)],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        raise ValueError('Replay verification tests failed; see verification.txt')
    results = []
    for index, case in enumerate(prepared['cases']):
        directory = output / 'cases' / case
        selected = [row for row in rows if row['source']['case'] == case]
        if case not in run['completed_cases']:
            case_results = [run_cell(row, directory / str(i), prepared) for i, row in enumerate(selected)]
            controls.write_json(directory / 'result.json', case_results)
            checkpoint = generation.output_checkpoint(directory)
            run['completed_cases'][case] = checkpoint
            run['result_files'][case] = checkpoint
            controls.write_json(output / 'run.json', run)
        checkpoint = run['completed_cases'][case]
        case_results = replay.read_json(Path(checkpoint['path']))
        if [r['source'] for r in case_results] != [r['source'] for r in selected]:
            raise ValueError('Case checkpoint source roster changed')
        results.extend(case_results)
        if (index + 1) % 10 == 0 or index + 1 == len(prepared['cases']):
            print(f"recorded {index + 1}/{len(prepared['cases'])} cases; {len(results)} original cells retained", flush=True)
    parent.verify_hashes(output, run)
    generation.verify_completed(run)
    run['source_inputs_unchanged'] = True
    errors = any(r['state'] == 'inspection_error' or any(v.get('state') in
        ('runtime_or_inspection_error', 'interrupted_execution_unknown', 'inspection_error') for v in r['conditions'].values()) for r in results)
    run['status'] = 'complete_with_errors' if errors else 'complete'
    run['evaluated_original_cells'] = sum(any(v.get('evaluated') for v in r['conditions'].values()) for r in results)
    controls.write_json(output / 'run.json', run)
    persist_report(output, run, results, summary)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
