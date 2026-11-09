#!/usr/bin/env python3
"""Classify saved evaluation evidence without executing or rescoring anything."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_oracle_coverage as oracle

generation = oracle.generation
controls, replay, parent = oracle.controls, oracle.replay, oracle.parent
CONFIG = ROOT / 'audit/v2/failure_attribution.json'
TESTS = ROOT / 'tests/unit/test_v2_failure_attribution.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/FAILURE_ATTRIBUTION.md']


def identity(row):
    return '/'.join((row['model'], row['method'], row['split'], row['instance'], str(int(row['sample_index']))))


def flag(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    if value in (0, 0.0, '0', '0.0'):
        return False
    if value in (1, 1.0, '1', '1.0'):
        return True
    raise ValueError('Only explicit binary recorded flags accepted')


def message_category(check):
    if check.get('status') == 'pass':
        return 'recorded_pass'
    message = check.get('message') or ''
    if message == 'scenario execution failed':
        return 'execution_error_propagated'
    if message.startswith('missing '):
        return 'missing_or_empty_output_message'
    if message.startswith('assertion evaluation error:'):
        return 'assertion_evaluation_error_message'
    if message.startswith(('value=', 'rows=', 'length=')):
        return 'value_or_count_mismatch_message'
    if message.startswith('unsupported assertion type'):
        return 'unsupported_assertion_type_message'
    if message.startswith('unexpected file '):
        return 'unexpected_output_message'
    return 'other_recorded_nonpass'


def report_observations(report):
    if not isinstance(report, dict):
        return {'available': False, 'recorded_status': None, 'observed_assertions': 0,
                'assertion_message_counts': {}, 'scenario_execution_failure': False,
                'scenario_alignment_failure': False}
    scenarios = report.get('scenarios') or []
    checks = [check for scenario in scenarios for check in scenario.get('assertions', [])]
    alignment = bool(report.get('unmatched_execution_scenarios') or report.get('unmatched_assertion_scenarios')
                     or any(s.get('scoring_error') for s in scenarios))
    execution_failure = any(s.get('execution_status') == 'fail' or s.get('execution_errors') for s in scenarios)
    reason = report.get('reason') or ''
    execution_failure = bool(execution_failure or reason.startswith('scenario execution failed:'))
    return {'available': True, 'recorded_status': report.get('overall_status', report.get('status')),
            'recorded_reason': reason, 'observed_assertions': len(checks),
            'recorded_assertions_total': report.get('assertions_total'),
            'recorded_assertions_passed': report.get('assertions_passed'),
            'assertion_message_counts': dict(Counter(message_category(check) for check in checks)),
            'scenario_execution_failure': execution_failure, 'scenario_alignment_failure': alignment,
            'checks': [{'scenario': s['scenario'], **check, 'message_category': message_category(check)}
                       for s in scenarios for check in s.get('assertions', [])]}


def classify(row, saved_ir_present, observation):
    """Mutually exclusive *recorded stage* categories, not causal diagnoses."""
    if flag(row['semantic_success']) is True:
        return 'published_end_to_end_pass'
    if row.get('run_validity') != 'valid':
        return 'invalid_observation'
    if not saved_ir_present:
        return 'no_saved_ir'
    if flag(row['executable_valid']) is False:
        return 'recorded_public_gate_failure'
    if observation['scenario_execution_failure']:
        return 'recorded_assertion_execution_failure'
    if observation['scenario_alignment_failure']:
        return 'recorded_assertion_scenario_alignment_failure'
    if not observation['available'] or observation['recorded_status'] in ('unscored', 'skipped', None):
        return 'assertion_record_unavailable_or_unscored'
    if not observation['observed_assertions']:
        return 'empty_or_nonvacuity_unverifiable_assertion_record'
    nonpass = sum(n for name, n in observation['assertion_message_counts'].items() if name != 'recorded_pass')
    if nonpass:
        return 'recorded_assertion_nonpass'
    return 'nonpass_not_explained_by_retained_assertion_checks'


def read_optional_json(path):
    if not path.is_file():
        return None, 'missing'
    try:
        value = replay.read_json(path)
        if not isinstance(value, dict):
            raise ValueError('Expected object')
        return value, 'present'
    except Exception as exc:
        return None, 'read_error:' + type(exc).__name__


def select_record(row, manifest, score, posthoc):
    """Use the same G6 evidence sources as the publication analysis."""
    expected_success = flag(row['semantic_success'])
    if row['split'] == 'main':
        if row['semantic_source'] != 'posthoc_scorer_1.2.1':
            raise ValueError('Unexpected Main publication source')
        key = '/'.join((row['model'], row['condition'], row['method'], row['split'], row['instance'], str(int(row['sample_index']))))
        result = posthoc['results'].get(key)
        if result is None or flag(result.get('semantic_success')) != expected_success:
            raise ValueError('Main post-hoc result disagrees with publication ledger')
        return result.get('g6_assert'), 'published_main_posthoc', result.get('status')
    if row['semantic_source'] != 'frozen_manifest_nonvacuous_assertions':
        raise ValueError('Unexpected non-Main publication source')
    if manifest is None:
        raise ValueError('Frozen source manifest unavailable')
    summary = (manifest.get('evaluation') or {}).get('score_summary') or {}
    # Match the publication preparation exactly: only an explicit JSON true
    # records a full pass. Missing scores on parse/public-invalid cells were
    # retained as non-passes, not silently removed from its denominator.
    if (summary.get('full_pass_g0_g6') is True) != expected_success:
        raise ValueError('Frozen manifest disagrees with publication ledger')
    return (score or {}).get('g6_assert'), 'frozen_score_file', None


def inspect_row(row, source, posthoc, scope):
    manifest_path = Path(source['manifest'])
    score_path = manifest_path.parent / 'score.json'
    manifest, manifest_state = read_optional_json(manifest_path)
    score, score_state = read_optional_json(score_path)
    report, evidence_source, posthoc_state = select_record(row, manifest, score, posthoc)
    observation = report_observations(report)
    present = Path(source['artifact']).is_file()
    category = classify(row, present, observation)
    return {'id': identity(row), 'model': row['model'], 'method': row['method'],
            'case': source['case'], 'split': row['split'], 'sample_index': int(row['sample_index']),
            'published_semantic_success': flag(row['semantic_success']),
            'published_executable_valid': flag(row['executable_valid']),
            'original_method_status': row['method_status'], 'run_validity': row['run_validity'],
            'published_first_failing_gate': row['first_failing_gate'] or None,
            'saved_ir_present': present, 'saved_ir_path': source['artifact'],
            'recorded_stage_category': category, 'assertion_evidence_source': evidence_source,
            'posthoc_record_status': posthoc_state, 'manifest_state': manifest_state,
            'score_state': score_state, 'score_path': str(score_path),
            'only_selected_status_telemetry_predicates': scope,
            'assertion_observations': observation,
            'interpretation': 'Recorded evidence only. Missing outputs do not establish whether naming, compilation, service execution, or model logic caused the failure.'}


def aggregate(records):
    groups = defaultdict(list)
    for row in records:
        groups[(row['model'], row['method'])].append(row)
    summaries = []
    for (model, method), rows in sorted(groups.items()):
        messages = Counter()
        for row in rows:
            messages.update(row.get('assertion_observations', {}).get('assertion_message_counts', {}))
        summaries.append({'model': model, 'method': method, 'declared_cells': len(rows),
            'published_passes': sum(row.get('published_semantic_success') is True for row in rows),
            'stage_counts': dict(Counter(row['recorded_stage_category'] for row in rows)),
            'assertion_message_counts': dict(messages),
            'cells_with_nonpass_message_category': dict(Counter(
                name for row in rows for name, n in row.get('assertion_observations', {}).get('assertion_message_counts', {}).items()
                if name != 'recorded_pass' and n))})
    return {'declared_cells': len(records), 'groups': summaries,
            'stage_counts': dict(Counter(row['recorded_stage_category'] for row in records)),
            'inspection_errors': sum(row['recorded_stage_category'] == 'inspection_error' for row in records),
            'note': 'Stage categories are exclusive; per-assertion message categories overlap at cell level. No new scores or causal effects are computed.'}


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference permitted')
    root = ROOT / design['parent_oracle_audit']
    previous = replay.read_json(root / 'run.json')
    if previous['status'] != 'complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged oracle audit required')
    hashes = parent.verify_hashes(root, previous)
    generation.verify_completed(previous)
    actual = {p.relative_to(root).as_posix(): controls.sha256(p) for p in (root / 'synthetic_controls').rglob('*') if p.is_file()}
    if actual != previous['synthetic_file_sha256']:
        raise ValueError('Prior synthetic control evidence changed')
    oracle_data = replay.read_json(root / 'evidence/result.json')
    scopes = {r['case']: r['only_selected_status_telemetry_predicates'] for r in oracle_data['corpus_inventory']}
    analysis = Path(design['publication_analysis'])
    csv_path = analysis / 'primary_run_level.csv'
    posthoc_path = analysis / 'posthoc_main_g6_assert.json'
    with csv_path.open(newline='') as handle:
        all_rows = list(csv.DictReader(handle))
    if len(all_rows) != design['expected_primary_cells'] or len({identity(r) for r in all_rows}) != len(all_rows):
        raise ValueError('Original primary publication roster changed')
    rows = [r for r in all_rows if r['method'] in design['methods']]
    coverage = ROOT / replay.read_json(generation.census.CONFIG)['parent_coverage'] / 'saved_cell_coverage.json'
    sources = {r['source']['id']: r['source'] for r in replay.read_json(coverage)}
    selected = {key: value for key, value in sources.items() if value['route'] == 'serviceflow_ir'}
    if len(rows) != design['expected_ir_cells'] or {identity(r) for r in rows} != set(selected):
        raise ValueError('IR ledger differs from original fixed source inventory')
    posthoc = replay.read_json(posthoc_path)
    if posthoc.get('status') != 'complete':
        raise ValueError('Completed publication post-hoc report required')
    paths = [*FILES, root / 'run.json', root / 'input_sha256.json', coverage, csv_path, posthoc_path]
    for saved in previous['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    paths.extend(root / name for name in previous['synthetic_file_sha256'])
    for row in rows:
        source = selected[identity(row)]
        if (Path(row['manifest_path']).resolve() != Path(source['manifest']).resolve()
                or source['case'] != row['split'] + '/' + row['instance']
                or source['case'] not in scopes):
            raise ValueError('Publication source identity/path mismatch')
        paths.extend([Path(source['manifest']), Path(source['artifact']), Path(source['manifest']).parent / 'score.json'])
    for path in paths:
        key = str(path.resolve())
        digest = controls.sha256(path) if path.is_file() else 'MISSING'
        if key in hashes and hashes[key] != digest:
            raise ValueError('Pinned original evidence changed')
        hashes[key] = digest
    return design, rows, selected, posthoc, scopes, hashes


def render(run, result):
    lines = ['# Recorded failure attribution (no rescoring)', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; original primary M3–M5 cells: {result['declared_cells']}.",
        'Uses the publication ledger, corrected Main post-hoc records, and retained non-Main score files.',
        'Zero model calls, runtime executions, or new semantic scores. M0–M2 are outside this G6-Assert analysis.', '',
        '## Recorded stage categories', '']
    lines.extend(f'- {name}: {count}' for name, count in sorted(result['stage_counts'].items()))
    lines += ['', '## By model and method', '',
        '| Model | Method | Declared | Published passes | No saved IR | Public gate failure | Assertion nonpass | Inspection errors |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for group in result['groups']:
        c = group['stage_counts']
        lines.append(f"| {group['model']} | {group['method']} | {group['declared_cells']} | {group['published_passes']} | {c.get('no_saved_ir', 0)} | {c.get('recorded_public_gate_failure', 0)} | {c.get('recorded_assertion_nonpass', 0)} | {c.get('inspection_error', 0)} |")
    messages = Counter()
    for group in result['groups']:
        messages.update(group['assertion_message_counts'])
    lines += ['', '## Recorded assertion-message counts (not cell counts)', '']
    lines.extend(f'- {name}: {count}' for name, count in sorted(messages.items()))
    lines += ['', '## Interpretation', '',
        'Missing/empty-output messages do not distinguish an unproduced artifact, path/mapping mismatch, empty file, or missing service semantics.',
        'Value/count mismatch messages are not automatically model reasoning errors; compiler/runtime behavior may also contribute.',
        'An unexecuted, unscored, or public-invalid cell is not direct evidence of incorrect business transformation.',
        'The telemetry-only inventory flag describes assertion scope, not a causal explanation for low pass rates.',
        'Stage categories are mutually exclusive under a fixed precedence; assertion-message categories can overlap within a cell.',
        'Unknown and inspection-error cells remain in the full denominator. Published scores and every original output remain unchanged.',
        'Keep evaluator-only details out of generation prompts. Use follow-up controls to test specific mapping/runtime hypotheses before making a causal claim.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying publication ledger and saved evaluation evidence (offline)...', flush=True)
    design, rows, sources, posthoc, scopes, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'primary_ir_cells': len(rows), 'models': sorted({r['model'] for r in rows}),
                          'methods': design['methods'], 'verified_inputs': len(hashes),
                          'main_source': 'publication posthoc_scorer_1.2.1',
                          'api_requests': 0, 'workflow_executions': 0, 'rescoring': False}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/evaluator_only' / f'package_v2_failure_attribution__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
           'status': 'running', 'result_files': {}, 'evidence_role': 'evaluator_only_never_model_context'}
    controls.write_json(output / 'input_sha256.json', hashes)
    controls.write_json(output / 'run.json', run)
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
    records = []
    for row in rows:
        source = sources[identity(row)]
        try:
            record = inspect_row(row, source, posthoc, scopes[source['case']])
        except Exception as exc:
            record = {'id': identity(row), 'model': row['model'], 'method': row['method'], 'case': source['case'],
                      'split': row['split'], 'sample_index': int(row['sample_index']),
                      'published_semantic_success': flag(row['semantic_success']),
                      'recorded_stage_category': 'inspection_error',
                      'error_type': type(exc).__name__, 'error_message': str(exc)}
        records.append(record)
    result = aggregate(records)
    if result['declared_cells'] != design['expected_ir_cells']:
        raise ValueError('Do not publish a partial attribution ledger')
    evidence = output / 'evidence'
    controls.write_json(evidence / 'cells.json', records)
    controls.write_json(evidence / 'result.json', result)
    run['result_files']['failure_attribution'] = generation.output_checkpoint(evidence)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if result['inspection_errors'] else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, result))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
