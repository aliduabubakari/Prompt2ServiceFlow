#!/usr/bin/env python3
"""Append the two declared Qwen seeds without changing frozen v2.3 methods."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_v2_fusion_v2_3 as frozen

ROOT = frozen.ROOT
SCRIPT = Path(__file__).resolve()
MANIFEST = ROOT / 'audit/v2/continuation.semantic-fusion.v2_3.qwen.json'
TESTS = ROOT / 'tests/unit/test_v2_fusion_qwen_continuation.py'
DOC = ROOT / 'audit/v2/SEMANTIC_FUSION_QWEN_CONTINUATION.md'
SOURCE = ROOT / 'audit/outputs/package_v2_fusion_v2_3__20261026T124819Z__09cf6fa7'
PREFIX = 'package_v2_fusion_v2_3_qwen_seeds__'


def key(cell): return '/'.join(map(str, cell))


def prepare_original():
    # The old freeze enumerates imported repository modules. Exclude only this
    # new orchestration entry point from that old inventory, then validate the
    # original freeze normally. It is pinned separately in MANIFEST. No method,
    # prompt, public tool or data file is excluded or edited.
    original = frozen.runner.implementation_files
    def original_files(): return [p for p in original() if p.resolve() != SCRIPT]
    frozen.runner.implementation_files = original_files
    try: return frozen.prepare()
    finally: frozen.runner.implementation_files = original


def continuation_spec(prepared, source_run):
    design = prepared['design']
    model = design['pilot_model']
    cells = [[model, method, seed] for seed in design['seeds'] for method in design['methods']]
    retained = [[model, method, design['pilot_seed']] for method in design['methods']]
    if (source_run['freeze'] != prepared['freeze'] or source_run['cells'] != retained
            or source_run['status'] != 'complete' or source_run.get('source_inputs_unchanged') is not True
            or source_run['controls_only'] is not False):
        raise ValueError('Source is not the completed unchanged v2.3 Qwen pilot')
    expected = {'controls', *(key(c) for c in retained)}
    if set(source_run['result_files']) != expected: raise ValueError('Source checkpoint roster differs')
    if len(cells) != 9 or len(retained) != 3 or design['seeds'] != [101, 202, 303]:
        raise ValueError('Expected the existing three-method, three-seed design')
    return {'continuation_id': 'p2sf-relational-v2.3-qwen-seeds/1',
        'method_freeze_id': prepared['freeze']['freeze_id'],
        'method_freeze_sha256': frozen.controls.sha256(frozen.FREEZE),
        'source_directory': str(SOURCE), 'source_run_sha256': frozen.controls.sha256(SOURCE / 'run.json'),
        'source_input_index_sha256': frozen.controls.sha256(SOURCE / 'input_sha256.json'),
        'model': model, 'case': design['case'], 'cells': cells, 'retained_cells': retained,
        'new_cells': [c for c in cells if c not in retained], 'images': source_run['images'],
        'implementation_sha256': {str(p): frozen.controls.sha256(p) for p in (SCRIPT, TESTS, DOC)},
        'interpretation': 'Development repetitions planned after inspecting seed 101; no held-out validation or corpus-wide success claim. Retain every result, including valid non-passes and invalid attempts.'}


def prepare(check_manifest=True):
    prepared = prepare_original()
    source_run = frozen.replay.read_json(SOURCE / 'run.json')
    frozen.parent.verify_hashes(SOURCE, source_run)
    frozen.generation.verify_completed(source_run)
    spec = continuation_spec(prepared, source_run)
    prepared['continuation'], prepared['source_run'] = spec, source_run
    if check_manifest:
        manifest = frozen.replay.read_json(MANIFEST)
        if manifest.get('status') != 'frozen' or manifest.get('specification') != spec:
            raise ValueError('Continuation manifest, implementation or source evidence differs')
        prepared['continuation_manifest'] = manifest
    prepared['hashes'] = {**prepared['hashes'], **spec['implementation_sha256'],
        str(SOURCE / 'run.json'): spec['source_run_sha256'],
        str(SOURCE / 'input_sha256.json'): spec['source_input_index_sha256']}
    if check_manifest: prepared['hashes'][str(MANIFEST)] = frozen.controls.sha256(MANIFEST)
    return prepared


def create_manifest():
    if MANIFEST.exists(): raise ValueError('Continuation manifest already exists; never overwrite it')
    prepared = prepare(False)
    result = {'status': 'frozen', 'created_at': datetime.now(timezone.utc).isoformat(),
              'specification': prepared['continuation']}
    frozen.controls.write_json(MANIFEST, result)
    return result


def verify_run(run, prepared):
    spec = prepared['continuation']
    if (run['continuation_manifest'] != prepared['continuation_manifest']
            or run['freeze'] != prepared['freeze'] or run['cells'] != spec['cells']
            or run['images'] != spec['images']
            or run['input_fingerprint'] != frozen.controls.fingerprint(prepared['hashes'])):
        raise ValueError('Continuation inputs, design, images or source differ; cannot resume')
    expected = {key(c) for c in spec['cells']} | {'controls'}
    if not set(run['result_files']).issubset(expected): raise ValueError('Undeclared checkpoint')
    for cell in spec['retained_cells']:
        if run['result_files'].get(key(cell)) != prepared['source_run']['result_files'][key(cell)]:
            raise ValueError('Retained seed-101 checkpoint differs from its original source')
    frozen.generation.verify_completed(run)


def write_report(output, run):
    frozen.runner.report(output, run)
    spec = run['continuation_manifest']['specification']
    rows = {k: frozen.replay.read_json(Path(v['path'])) for k, v in run['result_files'].items() if k != 'controls'}
    lines = ['', '## Qwen seed continuation', '',
        'Seed 101 is retained by immutable reference from the completed pilot, including its M5 non-pass.',
        'Only seeds 202 and 303 are newly dispatched. No model, method, budget, prompt, compiler or assertion change.',
        'These are repeated generations on one development task, not independent pipelines or held-out validation.', '',
        '| Method | Declared compositions | Recorded | Invalid | Public passes | All business checks pass |',
        '|---|---:|---:|---:|---:|---:|']
    for method in prepared_methods(spec):
        relevant = [v for v in rows.values() if v['method'] == method]
        lines.append(f"| {method} | 3 | {len(relevant)} | {sum(r['validity'] != 'valid' for r in relevant)} | "
            f"{sum(r['validity'] == 'valid' and r['evaluation'].get('public_overall') == 'pass' for r in relevant)} | "
            f"{sum(r['validity'] == 'valid' and r['evaluation'].get('business_pass') is True for r in relevant)} |")
    retained = {key(c) for c in spec['retained_cells']}
    lines += ['', f"Retained tokens: {sum(r.get('usage', {}).get('total_tokens', 0) for k, r in rows.items() if k in retained)}.",
        f"New-attempt tokens: {sum(r.get('usage', {}).get('total_tokens', 0) for k, r in rows.items() if k not in retained)}.",
        'Not-evaluated valid submissions remain non-passes; invalid attempts remain in coverage.',
        f"Source pilot: {spec['source_directory']}", '']
    with (output / 'summary.md').open('a') as handle: handle.write('\n'.join(lines))


def prepared_methods(spec): return list(dict.fromkeys(c[1] for c in spec['cells']))


def execute_pending(prepared, output, run):
    """Never automatically redispatch an interrupted or completed attempt."""
    for cell in prepared['continuation']['new_cells']:
        model, method, seed = cell
        identity = key(cell)
        if identity in run['result_files']: continue
        index = prepared['continuation']['cells'].index(cell)
        directory = output / 'cells' / f'{index:03d}_{model}_{method}_{seed}'
        if directory.exists():
            path = directory / 'result.json'
            if path.is_file():
                result = frozen.replay.read_json(path)
                if (result['model'], result['method'], result['seed'], result['case']) != (model, method, seed, prepared['design']['case']):
                    raise ValueError('Uncheckpointed result identity differs')
            else:
                result = {'model': model, 'method': method, 'seed': seed, 'case': prepared['design']['case'],
                    'validity': 'invalid_interrupted_attempt', 'usage': {},
                    'evaluation': {'state': 'interrupted_unknown_no_redispatch', 'evaluated': False}}
                frozen.controls.write_json(path, result)
        else:
            result = frozen.runner.execute_cell(prepared, model, method, seed, directory, True)
        run['result_files'][identity] = frozen.generation.output_checkpoint(directory)
        frozen.controls.write_json(output / 'run.json', run)
        print(f"recorded {model} {method} seed={seed}: {result['validity']}, {result['evaluation']['state']}", flush=True)


def run_locked(args, prepared):
    spec = prepared['continuation']
    if args.resume:
        output = args.resume.resolve()
        run = frozen.replay.read_json(output / 'run.json')
        verify_run(run, prepared)
    else:
        # One explicit continuation per manifest prevents accidental paid
        # duplicates when the default command is pasted a second time.
        existing = sorted((ROOT / 'audit/outputs').glob(PREFIX + '*/run.json'))
        if existing:
            raise ValueError('A continuation already exists; resume it with --resume ' + str(existing[-1].parent))
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'{PREFIX}{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': prepared['design']['package_version'], 'audit_protocol_version': prepared['design']['audit_protocol_version'],
            'freeze': prepared['freeze'], 'continuation_manifest': prepared['continuation_manifest'],
            'cells': spec['cells'], 'controls_only': False, 'images': spec['images'],
            'input_fingerprint': frozen.controls.fingerprint(prepared['hashes']),
            'status': 'running', 'result_files': {key(c): prepared['source_run']['result_files'][key(c)] for c in spec['retained_cells']},
            'environment': frozen.controls.environment()}
        frozen.controls.write_json(output / 'run.json', run)
        frozen.controls.write_json(output / 'input_sha256.json', prepared['hashes'])
    print('Output: ' + str(output), flush=True)
    pending = [c for c in spec['new_cells'] if key(c) not in run['result_files']]
    if pending:
        config = prepared['models'][spec['model']]
        if not os.environ.get(config.api_key_env): raise ValueError('Set ' + config.api_key_env + ' in this terminal; then resume this output directory')
        images = frozen.bridge.agent_module().inspect_image_digests()
        if images != spec['images']: raise ValueError('v2.3 image identities differ from the completed pilot; no inference dispatched')
        prepared['expected_images'] = images
        if 'controls' not in run['result_files']:
            tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(frozen.TESTS), str(TESTS)],
                cwd=ROOT, capture_output=True, text=True, timeout=120)
            (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
            if tests.returncode: raise ValueError('Offline verification failed; inspect verification.txt')
            control_dir = output / 'controls'
            if control_dir.exists():
                if not (control_dir / 'result.json').is_file(): raise ValueError('Interrupted controls: inspect this attempt before proceeding')
                control = frozen.replay.read_json(control_dir / 'result.json')
            else: control = frozen.runner.integration_controls(prepared, control_dir)
            run['result_files']['controls'] = frozen.generation.output_checkpoint(control_dir)
            frozen.controls.write_json(output / 'run.json', run)
        control = frozen.replay.read_json(Path(run['result_files']['controls']['path']))
        if not control['control_gate_pass']:
            run['status'] = 'control_gate_failed_no_inference'
            frozen.controls.write_json(output / 'run.json', run); write_report(output, run)
            print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
            return 1
        execute_pending(prepared, output, run)
    if set(run['result_files']) != {'controls', *(key(c) for c in spec['cells'])}:
        raise ValueError('Incomplete continuation checkpoint roster')
    frozen.parent.verify_hashes(output, run); frozen.generation.verify_completed(run)
    rows = [frozen.replay.read_json(Path(run['result_files'][key(c)]['path'])) for c in spec['cells']]
    run['invalid_cells'] = sum(r['validity'] != 'valid' for r in rows)
    run['source_inputs_unchanged'] = True
    run['status'] = 'complete_with_invalid_observations' if run['invalid_cells'] else 'complete'
    frozen.controls.write_json(output / 'run.json', run); write_report(output, run)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying frozen v2.3 inputs, completed pilot and continuation manifest...', flush=True)
    prepared = prepare()
    if args.dry_run:
        spec = prepared['continuation']
        print(json.dumps({k: spec[k] for k in ('case', 'model', 'retained_cells', 'new_cells', 'method_freeze_id')}, indent=2))
        print('Retained: 3 cells; new: 6 cells; total: 9. Dry-run model calls: 0.')
        return 0
    lock = ROOT / 'audit/outputs/.fusion-v2_3-qwen-continuation.lock'
    with lock.open('a') as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('A Qwen continuation is already running') from None
        return run_locked(args, prepared)


if __name__ == '__main__': raise SystemExit(main())
