#!/usr/bin/env python3
"""Evaluator-only synthetic counterexamples; never execute workflows or models."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_binding_assembly as assembly

generation = assembly.generation
controls, replay, parent = assembly.controls, assembly.replay, assembly.parent
CONFIG = ROOT / 'audit/v2/oracle_coverage_controls.json'
TESTS = ROOT / 'tests/unit/test_v2_oracle_coverage.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/ORACLE_COVERAGE_CONTROLS.md',
         ROOT / 'src/prompt2serviceflow/validators/instance_validation.py']


def contained(root, relative):
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts or '://' in relative):
        raise ValueError('Control paths must remain contained')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Control paths must remain contained')
    return path


def validate_assertions(assertions):
    scenarios = assertions.get('scenarios', [])
    if not scenarios or len({s['scenario'] for s in scenarios}) != len(scenarios):
        raise ValueError('Nonempty unique assertion scenarios required')
    for scenario in scenarios:
        name = scenario['scenario']
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name)):
            raise ValueError('Scenario names must be safe identifiers')
        rows = scenario['assertions']
        if not rows or len({r['assertion_id'] for r in rows}) != len(rows):
            raise ValueError('Nonempty unique assertion ids required')
        for row in rows:
            if row['type'] not in ('file_exists', 'json_path_equals', 'json_path_gte'):
                raise ValueError('New assertion type needs a separately reviewed control design')
            contained(ROOT / 'audit/evaluator_only', row['path'])
            if not row['path'].startswith('artifacts/'):
                raise ValueError('This bounded control expects artifact-only predicates')


def witness(condition, first_intent, last_intent):
    """Fixed diagnostic witnesses, never filled from expected assertion values.

    The counters and success claims are synthetic. This tests predicates, not
    whether actual workflow execution legitimately produced such claims.
    """
    source = {'success': True, 'fixture': {'file_count': 1, 'record_count': 1}}
    final = {'success': True, 'upstream_artifact_count': 1}
    files = {f'artifacts/{first_intent}_status.json': source,
             f'artifacts/{last_intent}_status.json': final}
    business = f'artifacts/{last_intent}_artifact.json'
    if condition == 'status_only_business_absent':
        pass
    elif condition == 'status_with_empty_business_payload':
        files[business] = []
    elif condition == 'status_with_unrelated_business_payload':
        files[business] = {'unrelated_diagnostic_control': 'No business transformation was run.'}
    elif condition == 'source_record_count_zero':
        source['fixture']['record_count'] = 0
    elif condition == 'final_success_false':
        final['success'] = False
    elif condition == 'upstream_count_zero':
        final['upstream_artifact_count'] = 0
    elif condition == 'final_status_missing':
        del files[f'artifacts/{last_intent}_status.json']
    else:
        raise ValueError('Unknown fixed witness condition')
    return files


def evaluate_scenario(rows, files, directory):
    directory.mkdir(parents=True, exist_ok=False)
    for relative, content in files.items():
        controls.write_json(contained(directory, relative), content)
    checks = []
    for assertion in rows:
        contained(directory, assertion['path'])
        try:
            passed, message = controls._evaluate_assertion(assertion, directory)
            status = 'pass' if passed else 'fail'
        except Exception as exc:
            status, message = 'error', type(exc).__name__ + ': ' + str(exc)
        checks.append({'assertion_id': assertion['assertion_id'], 'status': status, 'message': message})
    return {'all_predicates_pass': bool(checks) and all(row['status'] == 'pass' for row in checks),
            'predicate_count': len(checks), 'predicates_passed': sum(row['status'] == 'pass' for row in checks),
            'checks': checks, 'synthetic_files': sorted(files), 'workflow_executed': False,
            'semantic_correctness': 'not_established', 'model_performance_observation': False}


def inspect_case(case, workspace, instance, conditions, output):
    assertions = controls.load(instance / 'gold/assertions.yaml')
    validate_assertions(assertions)
    runtime = controls.load(instance / 'runtime/manifest.yaml')
    tasks = runtime['tasks']
    if not tasks or len({t['intent_id'] for t in tasks}) != len(tasks):
        raise ValueError('Nonempty unique reference task ids required')
    first, last = tasks[0]['intent_id'], tasks[-1]['intent_id']
    if first == last or not all(isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9_]*', name) for name in (first, last)):
        raise ValueError('This witness design requires distinct initial/final tasks')
    public_context = generation.census.public_context(workspace)
    private_names = {s['scenario'] for s in assertions['scenarios']}
    if private_names != {s['name'] for s in public_context['scenarios']}:
        raise ValueError('Public and assertion scenario rosters disagree')
    public_manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, public_manifest)
    cases = []
    inventory = []
    for scenario in assertions['scenarios']:
        rows = scenario['assertions']
        inventory.extend({'scenario': scenario['scenario'], 'assertion_id': row['assertion_id'],
                          'type': row['type'], 'path': row['path'], 'json_path': row.get('json_path')}
                         for row in rows)
        for condition in conditions:
            files = witness(condition, first, last)
            location = output / 'synthetic_controls' / case / scenario['scenario'] / condition
            row = evaluate_scenario(rows, files, location)
            row.update(case=case, scenario=scenario['scenario'], condition=condition)
            cases.append(row)
    return {'case': case, 'assertion_inventory': inventory, 'controls': cases,
            'oracle_paths': sorted({r['path'] for r in inventory}),
            'business_artifact_test_path': f'artifacts/{last}_artifact.json',
            'scope': 'Direct frozen assertion predicates only. No artifact remapping, full gate aggregation, or workflow success claim.'}


def predicate_inventory(case, assertions):
    rows = [{'scenario': scenario['scenario'], 'assertion_id': a['assertion_id'],
             'type': a['type'], 'path': a['path'], 'json_path': a.get('json_path')}
            for scenario in assertions['scenarios'] for a in scenario['assertions']]
    fields = {'success', 'fixture.file_count', 'fixture.record_count', 'upstream_artifact_count'}
    def telemetry(row):
        return (row['path'].endswith('_status.json') and
                (row['type'] == 'file_exists' or
                 (row['type'] in ('json_path_equals', 'json_path_gte') and
                  isinstance(row['json_path'], str) and row['json_path'] in fields)))
    return {'case': case, 'scenario_count': len(assertions['scenarios']), 'predicate_count': len(rows),
            'type_counts': dict(Counter(row['type'] for row in rows)), 'predicates': rows,
            'only_selected_status_telemetry_predicates': bool(rows) and all(telemetry(row) for row in rows),
            'scope': 'Path/field inventory only. A telemetry-focused oracle is not automatically inappropriate for every task.'}


def inventory_roster(base, strata):
    cases = sorted(f'{split}/{p.name}' for split in strata
                   for p in (base / 'cases' / split).iterdir() if p.is_dir())
    if dict(Counter(case.split('/')[0] for case in cases)) != strata:
        raise ValueError('Original corpus control roster changed')
    if any(not re.fullmatch(r'(main|validation|extension)/[a-z0-9_]+', case) for case in cases):
        raise ValueError('Unsafe inventory case id')
    return cases


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference permitted')
    root = ROOT / design['parent_assembly']
    previous = replay.read_json(root / 'run.json')
    if previous['status'] != 'complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged assembly evidence required')
    hashes = parent.verify_hashes(root, previous)
    generation.verify_completed(previous)
    family = replay.read_json(generation.CONFIG)['allowed_cases']
    if design['cases'] != family:
        raise ValueError('Retain the preselected family roster')
    inventory_file = ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json'
    inventory = replay.read_json(inventory_file)
    base = Path(inventory['control_directory'])
    paths = [*FILES, root / 'run.json', root / 'input_sha256.json', inventory_file]
    for case in inventory_roster(base, design['inventory_strata']):
        paths.append(controls.BENCHMARK / 'instances' / case / 'gold/assertions.yaml')
    for saved in previous['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    for case in family:
        instance = controls.BENCHMARK / 'instances' / case
        workspace = base / 'cases' / case / 'public_workspace' / case
        generation.census.public_context(workspace)
        manifest = controls.load(workspace / 'workspace.yaml')
        generation.verify_prompt_inventory(workspace, manifest)
        paths.extend(workspace / row['path'] for row in manifest['files'])
        paths.append(workspace / 'workspace.yaml')
        paths.extend(instance / name for name in ('gold/assertions.yaml', 'runtime/manifest.yaml'))
        # Preserve native implementation source for human review; never import
        # or execute it. No source-summary heuristic is treated as semantic proof.
        paths.extend((instance / 'runtime/scripts').glob('*.py'))
        validate_assertions(controls.load(instance / 'gold/assertions.yaml'))
    for path in paths:
        key, digest = str(path.resolve()), controls.sha256(path)
        if key in hashes and hashes[key] != digest:
            raise ValueError('Pinned evidence changed')
        hashes[key] = digest
    return design, previous, base, hashes


def render(run, results, inventory):
    lines = ['# Evaluator-only assertion coverage controls', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; preselected family: {len(results)} pipelines.",
        'Synthetic predicate controls only: zero API calls and zero workflow executions.',
        'These are not generated-submission scores, full-gate passes, or corrected semantic-success rates.', '',
        f"Corpus inventory: {len(inventory)} original pipelines; {sum(row['only_selected_status_telemetry_predicates'] for row in inventory)} use only the selected status telemetry predicates.",
        'The corpus figure inventories predicate scope; it is not a semantic-success or oracle-error rate.', '',
        '| Case | Scenario | Synthetic condition | Predicates passed | All pass |', '|---|---|---|---:|---|']
    for case in results:
        for row in case['controls']:
            lines.append(f"| {row['case']} | {row['scenario']} | {row['condition']} | {row['predicates_passed']}/{row['predicate_count']} | {row['all_predicates_pass']} |")
    lines += ['', '## Interpretation limits', '',
        'If status-only witnesses pass while the business artifact is absent, these predicates do not establish the business transformation.',
        'Rejected status mutations show which telemetry properties the predicates do check.',
        'Synthetic success claims are not authenticated execution results. Passing these predicates does not imply passing the entire evaluation.',
        'These controls test neither original false-negative rates nor the whole corpus. Weak coverage alone does not explain low original pass rates.',
        'Keep this evaluator-only evidence and private assertions out of prompts and repair rules. Do not fabricate a real submission to satisfy these checks.',
        'Business semantics, public source completeness, real implementations, and independent reference/mutation controls are still needed for v2.',
        'Original outputs, v1 scores, paper, and published deposit remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying evaluator-only sources and the completed assembly (offline)...', flush=True)
    design, previous, base, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'cases': design['cases'], 'conditions_per_scenario': len(design['conditions']),
                          'corpus_inventory_cases': sum(design['inventory_strata'].values()),
                          'verified_inputs': len(hashes), 'api_requests': 0, 'workflow_executions': 0,
                          'model_scores': False, 'private_evidence_role': 'evaluator_only'}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/evaluator_only' / f'package_v2_oracle_coverage__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
           'status': 'running', 'result_files': {}, 'evidence_role': 'evaluator_only_never_model_context'}
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
    inventory = [predicate_inventory(case, controls.load(controls.BENCHMARK / 'instances' / case / 'gold/assertions.yaml'))
                 for case in inventory_roster(base, design['inventory_strata'])]
    results = []
    for case in design['cases']:
        workspace = base / 'cases' / case / 'public_workspace' / case
        results.append(inspect_case(case, workspace, controls.BENCHMARK / 'instances' / case, design['conditions'], output))
    evidence = output / 'evidence'
    controls.write_json(evidence / 'result.json', {'evidence_role': run['evidence_role'], 'cases': results, 'corpus_inventory': inventory})
    run['result_files']['oracle_controls'] = generation.output_checkpoint(evidence)
    # Synthetic files are also evidence: fingerprint every witness separately.
    run['synthetic_file_sha256'] = {p.relative_to(output).as_posix(): controls.sha256(p)
                                  for p in (output / 'synthetic_controls').rglob('*') if p.is_file()}
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    errors = any(check['status'] == 'error' for case in results for row in case['controls'] for check in row['checks'])
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if errors else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, results, inventory))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
