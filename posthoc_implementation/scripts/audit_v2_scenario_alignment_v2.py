#!/usr/bin/env python3
"""Offline evaluator-only scenario coverage/provenance audit, no rescoring."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'audit/v2'), str(ROOT / 'audit')]
import replay_v2_csv_saved_ir as previous
import scenario_alignment_v2 as analysis

controls, replay = previous.controls, previous.replay
CONFIG = ROOT / 'audit/v2/scenario_alignment.v2.json'
TEST = ROOT / 'tests/unit/test_v2_scenario_alignment_v2.py'
DOC = ROOT / 'audit/v2/SCENARIO_ALIGNMENT_V2.md'
IMPLEMENTATION = [CONFIG, TEST, DOC, Path(__file__).resolve(), Path(analysis.__file__)]


def publication_key(row):
    return '/'.join((row['model'], row['condition'], row['method'], row['split'], row['instance'], str(int(row['sample_index']))))


def identity(row):
    return '/'.join((row['model'], row['method'], row['split'], row['instance'], str(int(row['sample_index']))))


def prepare():
    design = replay.read_json(CONFIG)
    if any(design[name] != 0 for name in ('maximum_inference_requests', 'maximum_runtime_executions', 'maximum_rescoring_calls')):
        raise ValueError('This audit permits no inference, runtime or rescoring calls')
    lock_path = ROOT / design['freeze_lock']; lock = replay.read_json(lock_path)
    if lock['protocol_version'] != design['protocol_version']: raise ValueError('Freeze version differs')
    previous.verify_named_inputs(ROOT, lock['files'], [p.relative_to(ROOT).as_posix() for p in IMPLEMENTATION])
    parent = ROOT / design['parent_replay']; old = replay.read_json(parent / 'run.json')
    if old['status'] != 'complete' or old.get('source_inputs_unchanged') is not True: raise ValueError('Completed unchanged replay required')
    hashes = previous.previous.prior.previous.coverage.frozen.parent.verify_hashes(parent, old)
    seal = replay.read_json(parent / 'output_sha256.json'); previous.verify_seal(parent, seal)
    if seal['output_fingerprint'] != design['parent_replay_output_fingerprint']: raise ValueError('Frozen replay evidence differs')
    paths = [*IMPLEMENTATION, lock_path, parent / 'output_sha256.json', *[parent / name for name in seal['files']]]
    attribution = ROOT / design['attribution_run']; saved = replay.read_json(attribution / 'run.json')
    if saved['status'] != 'complete' or saved.get('source_inputs_unchanged') is not True: raise ValueError('Completed unchanged attribution required')
    paths += [attribution / 'run.json', attribution / 'input_sha256.json']
    for record in saved['result_files'].values():
        for relative, sha in record['files'].items():
            path = Path(record['path']).parent / relative
            if controls.sha256(path) != sha: raise ValueError('Original attribution evidence changed')
            paths.append(path)
    records = replay.read_json(attribution / 'evidence/cells.json')
    if len(records) != design['expected_original_ir_cells'] or len({r['id'] for r in records}) != len(records): raise ValueError('Attribution roster differs')
    cells = sorted((r for r in records if r['recorded_stage_category'] == design['selected_stage']), key=lambda r: r['id'])
    if ([r['id'] for r in cells] != design['cell_ids'] or len(cells) != design['expected_selected_cells']
            or len({r['case'] for r in cells}) != design['expected_cases']): raise ValueError('Frozen 37-cell selection differs')
    publication = Path(design['publication_analysis']); ledger_path = publication / 'primary_run_level.csv'
    posthoc_path = publication / 'posthoc_main_g6_assert.json'; paths += [ledger_path, posthoc_path]
    with ledger_path.open(newline='') as stream: entries = list(csv.DictReader(stream))
    if len(entries) != 5940 or len({identity(r) for r in entries}) != len(entries): raise ValueError('Publication ledger differs')
    ledger = {identity(r): r for r in entries}; posthoc = replay.read_json(posthoc_path)
    if posthoc['status'] != 'complete': raise ValueError('Completed corrected publication report required')
    directories = {}
    for cell in cells:
        row = ledger[cell['id']]
        if row['split'] != 'main' or row['semantic_source'] != 'posthoc_scorer_1.2.1' or row['semantic_success'] != '0':
            raise ValueError('Selection differs from published nonpass evidence')
        if row['split'] + '/' + row['instance'] != cell['case']: raise ValueError('Case identity differs')
        post = posthoc['results'][publication_key(row)]
        if post['semantic_success'] is not False: raise ValueError('Post-hoc result differs')
        submission = Path(cell['saved_ir_path']).parent
        workspace = Path(design['original_workspace_root']) / cell['case']
        instance = ROOT / design['benchmark_root'] / 'instances' / cell['case']
        paths += [Path(cell['saved_ir_path']), Path(cell['score_path']), Path(row['manifest_path']),
                  submission / 'runtime/manifest.yaml', workspace / 'workspace.yaml',
                  instance / 'runtime/manifest.yaml', instance / 'gold/assertions.yaml']
        workspace_index = analysis.document(workspace / 'workspace.yaml')
        paths += [analysis.bounded.safe(workspace, r['path']) for r in workspace_index['files']]
        for directory in (workspace / 'fixtures', instance / 'fixtures', submission / 'runtime'):
            snapshot = analysis.tree(directory); directories[str(directory)] = snapshot
            paths += [analysis.bounded.safe(directory, name) for name in snapshot['files']]
        assertions = analysis.document(instance / 'gold/assertions.yaml')
        # Pin absent expected files too; creating one later cannot silently
        # change the original-output inventory used in this analysis.
        paths += [analysis.bounded.safe(submission, a['path']) for s in assertions['scenarios'] for a in s['assertions']]
    for path in paths:
        key = str(path.resolve()); value = controls.sha256(path) if path.is_file() else 'MISSING'
        if key in hashes and hashes[key] != value: raise ValueError('Pinned evidence changed: ' + key)
        hashes[key] = value
    return {'design': design, 'cells': cells, 'ledger': ledger, 'posthoc': posthoc, 'hashes': hashes, 'directory_inventories': directories}


def verify_directories(inventories):
    for name, expected in inventories.items():
        if analysis.tree(Path(name)) != expected: raise ValueError('Evidence directory inventory changed: ' + name)


def inspect_one(cell, prepared):
    d = prepared['design']; row = prepared['ledger'][cell['id']]
    return analysis.inspect(cell, row, prepared['posthoc']['results'][publication_key(row)],
                            ROOT / d['benchmark_root'], Path(d['original_workspace_root']) / cell['case'])


def aggregate(records, design):
    inspected = [r for r in records if r['state'] == 'inspected']
    return {'declared_cells': design['expected_selected_cells'], 'recorded_cells': len(records),
        'inspected_cells': len(inspected), 'inspection_errors': len(records) - len(inspected),
        'cases': len({r['case'] for r in records}), 'verified_public_provenance_cells': sum(r['public_provenance']['verified'] for r in inspected),
        'cells_with_supported_input_association': sum(bool(r['supported_input_associations']) for r in inspected),
        'cells_with_uncovered_reviewed_scenarios': sum(bool(r['reviewed_scenarios_without_supported_association']) for r in inspected),
        'cells_with_additional_execution_lower_bound': sum(r['additional_recorded_executions_required_lower_bound'] > 0 for r in inspected),
        'cells_with_loose_expected_output_files': sum(r['retained_outputs']['loose_expected_files_present'] > 0 for r in inspected),
        'provenance_bound_snapshot_cells': sum(r['retained_outputs']['provenance_bound_snapshot_available'] for r in inspected),
        'new_semantic_scores': 0, 'runtime_executions': 0, 'llm_calls': 0, 'rescoring_calls': 0}


def render(output, run, records):
    totals = aggregate(records, run['design']); controls.write_json(output / 'aggregate.json', totals)
    lines = ['# Evaluator-only scenario alignment audit', '', 'Status: ' + run['status'], '', run['design']['scope'], '',
        '| Coverage/diagnostic | Cells |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in totals.items()]
    lines += ['', '## By task', '', '| Task | Declared | Inspected | Verified public inputs | Supported input association | Missing reviewed coverage | Additional execution needed, lower bound |', '|---|---:|---:|---:|---:|---:|---:|']
    for case in sorted({r['case'] for r in records}):
        rows = [r for r in records if r['case'] == case]; good = [r for r in rows if r['state'] == 'inspected']
        values = [len(rows), len(good), sum(r['public_provenance']['verified'] for r in good),
                  sum(bool(r['supported_input_associations']) for r in good),
                  sum(bool(r['reviewed_scenarios_without_supported_association']) for r in good),
                  sum(r['additional_recorded_executions_required_lower_bound'] for r in good)]
        lines.append('| ' + case + ' | ' + ' | '.join(map(str, values)) + ' |')
    lines += ['', '## Interpretation', '',
        'Different scenario names alone do not establish a naming-only error. Supported associations require verified public input provenance, equal parameter maps and exact complete fixture-tree hashes with an unambiguous association.',
        'Additional-execution lower bounds compare recorded execution count with required reviewed scenario count. They do not identify which unmatched scenario ran under an unknown name.',
        'Loose output files and static generated writer code are not execution snapshots. This audit does not reconstruct outputs, invoke assertions or compute corrected scores.',
        'Any required scenario lacking supported execution evidence remains untested/unresolved. Published nonpasses are preserved; they are not relabeled as demonstrated business failures or passes.',
        'All detailed metadata are evaluator-only. Do not use these files in model prompts.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def seal_output(output):
    files = previous.snapshot_files(output); files.pop('output_sha256.json', None)
    controls.write_json(output / 'output_sha256.json', {'files': files, 'output_fingerprint': controls.fingerprint(files),
        'self_excluded': 'output_sha256.json', 'seal_stage': 'end-of-invocation'})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--dry-run', action='store_true'); args = parser.parse_args(argv)
    print('Verifying frozen 37-cell selection, original publication evidence and fixture inventories...', flush=True)
    p = prepare(); d = p['design']
    if args.dry_run:
        print(json.dumps({'selected_cells': len(p['cells']), 'cases': len({c['case'] for c in p['cells']}),
            'verified_input_pins': len(p['hashes']), 'evidence_directories': len(p['directory_inventories']),
            'llm_calls': 0, 'runtime_executions': 0, 'rescoring_calls': 0}, indent=2)); return 0
    output = ROOT / 'audit/evaluator_only' / ('package_v2_scenario_alignment__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    run = {'status': 'prepared', 'design': d, 'input_fingerprint': controls.fingerprint(p['hashes']), 'completed_cells': {},
           'directory_inventories': p['directory_inventories'], 'evidence_role': 'evaluator_only_never_model_context',
           'llm_calls': 0, 'runtime_executions': 0, 'rescoring_calls': 0}
    controls.write_json(output / 'input_sha256.json', p['hashes']); controls.write_json(output / 'run.json', run)
    controls.write_json(output / 'frozen_roster.json', [{'id': c['id'], 'case': c['case'], 'source_stage': c['recorded_stage_category']} for c in p['cells']])
    for path in [*IMPLEMENTATION, ROOT / d['freeze_lock']]:
        destination = output / 'implementation' / path.relative_to(ROOT); destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, destination)
    print('Output: ' + str(output), flush=True); records = []
    try:
        tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TEST)], cwd=ROOT, text=True, capture_output=True, timeout=60)
        (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
        if tests.returncode: raise ValueError('Synthetic provenance verification failed')
        run['status'] = 'running'
        for cell in p['cells']:
            try: record = inspect_one(cell, p)
            except Exception as exc:
                record = {'id': cell['id'], 'case': cell['case'], 'model': cell['model'], 'method': cell['method'],
                          'state': 'inspection_error', 'error_type': type(exc).__name__, 'message': str(exc)[:1200], 'rescored': False}
            records.append(record)
            path = output / 'cells' / cell['id'] / 'result.json'; controls.write_json(path, record)
            run['completed_cells'][cell['id']] = {'path': str(path), 'sha256': controls.sha256(path)}
            controls.write_json(output / 'run.json', run)
            print(cell['id'] + ': ' + record['state'], flush=True)
        if len(records) != d['expected_selected_cells'] or {r['id'] for r in records} != set(d['cell_ids']): raise ValueError('Do not publish partial or changed coverage')
        previous.previous.prior.previous.coverage.frozen.parent.verify_hashes(output, run)
        verify_directories(p['directory_inventories']); run['source_inputs_unchanged'] = True
        run['status'] = 'complete' if all(r['state'] == 'inspected' for r in records) else 'complete_with_inspection_errors'
    except BaseException as exc:
        run['status'] = 'interrupted_or_error'; run['error'] = type(exc).__name__ + ': ' + str(exc)[:1200]
        controls.write_json(output / 'run.json', run); render(output, run, records); seal_output(output); raise
    controls.write_json(output / 'run.json', run); render(output, run, records); seal_output(output)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
