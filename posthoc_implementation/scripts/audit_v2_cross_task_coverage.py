#!/usr/bin/env python3
"""Offline 110-task real-operation/public-input coverage; never generation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import io
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'audit/v2'))
import continue_v2_fusion_deepseek as anchor
import task_coverage_analysis as analysis

frozen, controls, replay = anchor.frozen, anchor.frozen.controls, anchor.frozen.replay
CONFIG = ROOT / 'audit/v2/cross_task_coverage.v1.json'
TESTS = ROOT / 'tests/unit/test_v2_cross_task_coverage.py'
DOC = ROOT / 'audit/v2/CROSS_TASK_COVERAGE.md'
ENTRY_POINTS = {Path(__file__).resolve(), Path(analysis.__file__).resolve()}


def prepare_anchor():
    # These new planning files are separately pinned below, not silently added
    # to the frozen method implementation. Nested continuations verify their
    # own separately pinned entry points; no public tool/data file is excluded.
    inventory = frozen.runner.implementation_files
    def original_inventory(): return [p for p in inventory() if p.resolve() not in ENTRY_POINTS]
    frozen.runner.implementation_files = original_inventory
    try: return anchor.prepare()
    finally: frozen.runner.implementation_files = inventory


def registered_backends():
    window = analysis.registry_keys(ROOT / 'audit/v2/bounded_window_executor.py', 'OPERATIONS')
    relational = analysis.registry_keys(ROOT / 'audit/v2/fusion_backend.py', 'OPERATIONS')
    csv_services = analysis.constant_strings(ROOT / 'audit/v2/workflow_executor.py', {'SENSOR', 'CSV', 'EXPORT'})
    helpers = analysis.registry_keys(ROOT / 'audit/service_executor_v3.py', 'REGISTRY')
    def pairs(values): return {(v, '1.0.0') for v in values}
    return {'window': {'services': pairs(window), 'exact_roster': True, 'method_route': True},
            'relational': {'services': pairs(relational), 'exact_roster': True, 'method_route': True},
            'csv_mechanism': {'services': pairs(csv_services), 'exact_roster': False, 'method_route': False},
            'isolated_port_helpers': {'services': pairs(helpers), 'exact_roster': False, 'method_route': False}}


def prepare():
    p = prepare_anchor()
    config = replay.read_json(CONFIG)
    source = ROOT / config['anchor_run']; completed = replay.read_json(source / 'run.json')
    anchor.verify_run(completed, p)
    frozen.parent.verify_hashes(source, completed)
    if completed['status'] not in ('complete', 'complete_with_invalid_observations') or completed.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged two-model evidence required')
    census = ROOT / config['census_run']; census_run = replay.read_json(census / 'run.json')
    if census_run['status'] != 'complete' or census_run.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged reference census required')
    cases = census_run['cases']
    if (len(cases) != config['expected_pipelines'] or len(set(cases)) != len(cases)
            or Counter(c.split('/')[0] for c in cases) != config['expected_strata']):
        raise ValueError('Original 110-task/stratum roster differs')
    if set(cases) != set(census_run['completed_cases']): raise ValueError('Reference census checkpoint roster differs')
    hashes = dict(p['hashes'])
    extra = [*ENTRY_POINTS, CONFIG, TESTS, DOC, ROOT / config['scope_reviews'],
        source / 'run.json', source / 'input_sha256.json', census / 'run.json', census / 'input_sha256.json',
        ROOT / 'audit/v2/bounded_window_executor.py', ROOT / 'audit/v2/fusion_backend.py',
        ROOT / 'audit/v2/workflow_executor.py', ROOT / 'audit/service_executor_v3.py']
    reviews = replay.read_json(ROOT / config['scope_reviews'])['tasks']
    if not set(reviews).issubset(cases): raise ValueError('Scope review references undeclared task')
    for review in reviews.values(): extra += [ROOT / review['profile_file'], *(ROOT / n for n in review['evidence'])]
    references = {}
    for case in cases:
        if not isinstance(case, str) or not re.fullmatch(r'(main|validation|extension)/[a-z0-9_]+', case):
            raise ValueError('Unsafe case identity')
        workspace = ROOT / config['public_baseline'] / case / 'public_workspace' / case
        reference = controls.BENCHMARK / 'instances' / case / 'gold/serviceflow.yaml'
        checkpoint = census_run['completed_cases'][case]; record_path = Path(checkpoint['path'])
        if controls.sha256(record_path) != checkpoint['sha256']: raise ValueError('Reference census checkpoint changed')
        record = replay.read_json(record_path)['reference']
        if record['case'] != case or record['reference_ir_sha256'] != controls.sha256(reference):
            raise ValueError('Reference service-roster source changed')
        # Full model observations in census files never enter classification.
        references[case] = (workspace, reference)
        extra += [reference, record_path]
        extra += [analysis.contained(workspace, path.relative_to(workspace))
                  for path in workspace.rglob('*') if path.is_file()]
    for path in extra:
        path = path.resolve(); digest = controls.sha256(path)
        if str(path) in hashes and hashes[str(path)] != digest: raise ValueError('Pinned source differs: ' + str(path))
        hashes[str(path)] = digest
    return {'config': config, 'cases': cases, 'references': references, 'reviews': reviews,
            'backends': registered_backends(), 'hashes': hashes}


def inspect_case(case, p):
    workspace, reference = p['references'][case]
    public = analysis.public_inventory(workspace, controls.load, controls.sha256)
    inputs = analysis.input_inventory(workspace, p['config']['max_public_file_bytes'])
    ir = controls.load(reference)
    bindings = [{'service_id': b['service_id'], 'service_version': b['service_version']} for b in ir['bindings']]
    review = p['reviews'].get(case)
    profile = analysis.profile_checks(inputs, review, lambda name: replay.read_json(analysis.contained(ROOT, name)))
    row = analysis.classify(case, bindings, p['backends'], inputs, review, profile)
    row.update(public_task_sha256=public['task_sha256'], public_review_signals=public['review_signals'],
        verified_public_files=public['verified_public_files'], public_inputs=inputs,
        reference_ir_sha256=controls.sha256(reference),
        control_structure={'branches': len(ir.get('control_flow', {}).get('branches', [])),
                           'gates': len(ir.get('control_flow', {}).get('gates', [])),
                           'parallel_groups': len(ir.get('control_flow', {}).get('parallel_groups', []))})
    if any(row['control_structure'][k] for k in ('branches', 'gates')):
        row['input_findings'].append('reference_control_semantics_require_backend_specific_review')
    return row


def render(output, run, rows):
    summary = analysis.summarize(rows)
    controls.write_json(output / 'coverage.json', rows)
    controls.write_json(output / 'aggregate.json', summary)
    controls.write_json(output / 'review_queue.json', summary['review_queue'])
    controls.write_json(output / 'implementation_backlog.json', summary['implementation_backlog'])
    stream = io.StringIO(newline='')
    fields = ['case', 'stratum', 'state', 'reference_service_count', 'unique_reference_services', 'registered_services',
              'missing_services', 'complete_backend_rosters', 'existing_development_case', 'original_task_semantics',
              'input_findings', 'new_generation_ready']
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(row.get(k)) if isinstance(row.get(k), (list, dict)) else row.get(k) for k in fields})
    (output / 'coverage.csv').write_text(stream.getvalue())
    lines = ['# Cross-task real-runtime and public-input coverage', '',
        f"State: {run['status']}; inspected {len(rows)} of {len(run['cases'])} pipelines.",
        'Zero LLM calls, workflow executions, repairs or new semantic scores. Original methods/results unchanged.',
        'Service-roster coverage is an upper bound; full public-task intent and execution readiness are not certified by this static audit.', '',
        '| State | Tasks |', '|---|---:|']
    lines += [f'| {state} | {n} |' for state, n in sorted(summary['states'].items())]
    lines += ['', '## Complete registered backend rosters', '',
        '| Task | Backend roster | Task interpretation | Input/profile findings |', '|---|---|---|---|']
    for row in rows:
        if row.get('complete_backend_rosters'):
            lines.append(f"| {row['case']} | {', '.join(row['complete_backend_rosters'])} | {row['original_task_semantics']} | {', '.join(row['input_findings']) or 'none found structurally'} |")
    lines += ['', 'Existing development tasks are not new-task validation candidates. Their documented intent gaps remain explicit.',
        'No new generation is authorized by this report. M0-M2 still need their separate direct-Argo business execution route.', '',
        '## New-task implementation/public-contract review queue', '',
        'Ranked from reference/public requirements only, without model outcomes. A high rank is not execution eligibility.', '',
        '| Rank | Task | Missing services | Input findings | State |', '|---:|---|---:|---:|---|']
    for item in summary['review_queue'][:15]:
        lines.append(f"| {item['rank']} | {item['case']} | {len(item['missing_services'])} | {len(item['input_findings'])} | {item['state']} |")
    lines += ['', 'Read coverage.json for named public sources, explicit profile checks and scope-review notes; read implementation_backlog.json for missing services.',
        'Next: review task semantics and missing inputs/operations, implement shared operations when justified, then run reference/numerical/rejection/mutant controls before freezing a multi-task generation design.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying immutable evidence and the 110-task reference/public roster (offline)...', flush=True)
    p = prepare()
    if args.dry_run:
        print(json.dumps({'pipelines': len(p['cases']), 'strata': p['config']['expected_strata'],
            'backend_service_counts': {k: len(v['services']) for k, v in p['backends'].items()},
            'llm_calls': 0, 'workflow_executions': 0, 'new_generation_authorized': False}, indent=2)); return 0
    if args.resume:
        output = args.resume.resolve(); run = replay.read_json(output / 'run.json')
        if run['input_fingerprint'] != controls.fingerprint(p['hashes']) or run['cases'] != p['cases']:
            raise ValueError('Audit implementation, public sources or policy differs; cannot resume')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_task_coverage__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'protocol_version': p['config']['protocol_version'], 'design': p['config'],
            'cases': p['cases'], 'completed_cases': {}, 'input_fingerprint': controls.fingerprint(p['hashes']),
            'llm_calls': 0, 'workflow_executions': 0, 'semantic_scores': 0, 'new_generation_authorized': False}
        controls.write_json(output / 'input_sha256.json', p['hashes'])
    print('Output: ' + str(output), flush=True)
    import subprocess
    tested = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tested.stdout + tested.stderr)
    if tested.returncode: raise ValueError('Offline audit verification failed; inspect verification.txt')
    run['status'] = 'running'; controls.write_json(output / 'run.json', run)
    rows = []
    for index, case in enumerate(p['cases']):
        if case in run['completed_cases']:
            saved = run['completed_cases'][case]; path = Path(saved['path'])
            if controls.sha256(path) != saved['sha256']: raise ValueError('Completed audit row changed')
            row = replay.read_json(path)
            if row['case'] != case: raise ValueError('Audit row identity differs')
        else:
            try: row = inspect_case(case, p)
            except Exception as exc:
                row = {'case': case, 'stratum': case.split('/')[0], 'state': 'inspection_error',
                       'error_type': type(exc).__name__, 'error': str(exc), 'new_generation_ready': False}
            path = output / 'cases' / case / 'coverage.json'; controls.write_json(path, row)
            run['completed_cases'][case] = {'path': str(path), 'sha256': controls.sha256(path)}
            controls.write_json(output / 'run.json', run)
        rows.append(row)
        print(f"[{index+1}/{len(p['cases'])}] {case}: {row['state']}", flush=True)
    frozen.parent.verify_hashes(output, run)
    run['source_inputs_unchanged'] = True
    run['status'] = 'complete_with_errors' if any(r['state'] == 'inspection_error' for r in rows) else 'complete'
    controls.write_json(output / 'run.json', run); render(output, run, rows)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
