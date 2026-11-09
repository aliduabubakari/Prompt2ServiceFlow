#!/usr/bin/env python3
"""Reusable completion and real execution of the saved model answer; no inference."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_generation_pilot as pilot
import semantic_completion

generation, controls, replay, parent = pilot.generation, pilot.controls, pilot.replay, pilot.parent
CONFIG = ROOT / 'audit/v2/semantic_resolution.json'
TESTS = ROOT / 'tests/unit/test_v2_semantic_resolution.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/semantic_completion.py',
         ROOT / 'audit/v2/SEMANTIC_RESOLUTION.md']


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference permitted')
    root = ROOT / design['source_pilot']
    source = replay.read_json(root / 'run.json')
    if source['status'] != 'complete' or source.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged source pilot required')
    hashes = parent.verify_hashes(root, source)
    generation.verify_completed(source)
    if pilot.file_hashes(root / 'evaluation_fixtures') != source['evaluation_fixture_files']:
        raise ValueError('Source evaluation inputs changed')
    if not (source['generation'].get('schema_conformant') and source['generation'].get('metadata_conformant')):
        raise ValueError('This correction requires a saved schema-conformant answer with valid public identity')
    ir = replay.read_json(root / 'generation/expanded_ir.json')
    if not all(ir[k] == source['metadata'][k] for k in generation.compact_ir.BOOKKEEPING):
        raise ValueError('Source public metadata disagrees')
    inventory = replay.read_json(ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json')
    workspace = Path(inventory['control_directory']) / 'cases' / source['design']['case'] / 'public_workspace' / source['design']['case']
    context = generation.census.public_context(workspace)
    manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, manifest)
    schema = controls.load(workspace / 'schemas/serviceflow_ir.schema.json')
    contract = replay.read_json(ROOT / design['projection_contract'])
    policy = replay.read_json(ROOT / design['assembly_policy'])
    if contract['profile_version'] != source['profile']['profile_version']:
        raise ValueError('Projection and numerical profiles disagree')
    catalog = generation.census.Catalog()
    candidate, decisions = semantic_completion.complete(ir, lambda s, v: catalog.get(workspace, s, v), contract, policy)
    inspected = pilot.inspect_candidate(candidate, schema, workspace, context, source['profile'])
    paths = [*FILES, ROOT / design['projection_contract'], ROOT / design['assembly_policy'], root / 'run.json', root / 'input_sha256.json']
    for saved in source['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    return design, source, ir, candidate, decisions, inspected, schema, workspace, context, root / 'evaluation_fixtures', hashes


def render(run):
    row = run['outcome']
    lines = ['# V2 integrated completion and semantic execution', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; model {run['model_id']}.",
        'Same saved model answer; zero new LLM calls. New declared compiler-completion condition.', '',
        f"- Completion state: {run['completion']['state']}",
        f"- Recorded completion/assembly operations: {len(run['completion']['operations'])}",
        f"- Execution state: {row['state']}",
        f"- Positive business-output cases: {str(row['positive_passes']) + '/6' if row.get('evaluated') else 'not executed'}",
        f"- Correct input rejections: {str(row['correct_rejections']) + '/3' if row.get('evaluated') else 'not executed'}", '',
        'Services, parameters, inputs, business artifacts and control edges are preserved. The only added binding is a uniquely declared registered auxiliary report projection.',
        'The report contents are computed by the real publisher, never filled from expected answers. All edits and remaining diagnostics are saved.',
        'A pass supports this saved composition under the explicit v2 profile, not a corpus-wide rate or corrected v1 score.',
        'Original generation, failed conditions, benchmark, paper, scores and published deposit remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying saved answer and compiling typed output completion (no LLM)...', flush=True)
    design, source, original, candidate, decisions, inspected, schema, workspace, context, fixtures, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'source_model': source['model_id'], 'source_case': source['design']['case'],
            'completion_state': decisions['state'], 'operations': len(decisions['operations']),
            'runtime_readiness': inspected['state'], 'api_requests': 0,
            'positive_scenarios': 6, 'expected_rejections': 3, 'verified_inputs': len(hashes)}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/outputs' / f'package_v2_semantic_resolution__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
        'design': design, 'model_id': source['model_id'], 'input_fingerprint': controls.fingerprint(hashes),
        'environment': controls.environment(), 'status': 'running', 'completion': decisions, 'result_files': {}}
    controls.write_json(output / 'run.json', run)
    controls.write_json(output / 'input_sha256.json', hashes)
    controls.write_json(output / 'completion.json', decisions)
    for path in [*FILES, ROOT / design['projection_contract'], ROOT / design['assembly_policy']]:
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
    if decisions['state'] == 'blocked_no_changes':
        row = {'state': 'completion_ambiguous', 'evaluated': False, 'reason': decisions['reason']}
        attempt = output / 'execution_attempt'; attempt.mkdir()
        controls.write_json(attempt / 'result.json', row)
    else:
        attempt = output / 'execution_attempt'
        row = pilot.run_condition(attempt, candidate, schema, workspace, context, source['profile'], fixtures,
                                  source['design'], decisions)
    run['outcome'] = row
    run['result_files']['semantic_resolution'] = generation.output_checkpoint(attempt)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    run['status'] = 'inputs_changed' if not unchanged else 'complete' if row.get('profile_all_controls_pass') is True else 'unresolved'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
