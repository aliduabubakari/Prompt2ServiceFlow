#!/usr/bin/env python3
"""Rerun the bounded IR pair with an observed reasoning-control setting."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_generation_pilot as generation

controls, replay, parent = generation.controls, generation.replay, generation.parent
CONFIG = ROOT / 'audit/v2/reasoning_generation.json'
TESTS = ROOT / 'tests/unit/test_v2_reasoning_generation.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/REASONING_GENERATION.md']


def build_requests(design, baseline):
    """Keep every pipeline prompt, seed, and token setting unchanged."""
    if (design['request_override'] != {'reasoning_effort': 'none'}
            or list(baseline) != design['conditions']
            or len(baseline) != design['maximum_inference_requests']):
        raise ValueError('Unexpected fixed pilot design')
    requests = copy.deepcopy(baseline)
    for request in requests.values():
        if 'reasoning_effort' in request:
            raise ValueError('Baseline already has a reasoning setting')
        request.update(design['request_override'])
    return requests


def check_probe(run):
    if run['status'] != 'complete' or run.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged reasoning probe required')
    rows = run['results']
    for condition in ('server_default', 'reasoning_effort_none'):
        if rows[condition].get('probe_success') is not True:
            raise ValueError('Both exact-JSON probe controls must pass')
    counts = [sum(rows[k].get('reasoning_character_counts', {}).values())
              for k in ('server_default', 'reasoning_effort_none')]
    if counts[0] <= 0 or counts[1] != 0:
        raise ValueError('Expected observed reasoning-control effect is absent')


def prepare():
    design = replay.read_json(CONFIG)
    args = argparse.Namespace(model=design['model_id'], instance=design['case'], max_output_tokens=None)
    (_, base_id, model, case, workspace, context, schema, metadata,
     codec, baseline, hashes) = generation.prepare(args)
    for key in ('parent_generation', 'parent_probe'):
        folder = ROOT / design[key]
        run = replay.read_json(folder / 'run.json')
        if run['status'] != 'complete' or run.get('source_inputs_unchanged') is not True:
            raise ValueError('Completed unchanged parent evidence required')
        verified = parent.verify_hashes(folder, run)
        generation.verify_completed(run)
        if any(path in hashes and hashes[path] != sha for path, sha in verified.items()):
            raise ValueError('Parent input fingerprints conflict')
        hashes.update(verified)
        if key == 'parent_generation':
            if (run['requests'] != baseline or run['model_id'] != base_id
                    or run['model_config'] != model or run['case'] != case):
                raise ValueError('Public requests/configuration differ from the earlier pair')
        else:
            check_probe(run)
            if run['design']['model_id'] != base_id:
                raise ValueError('Probe model differs from generation model')
        paths = [folder / 'run.json', folder / 'input_sha256.json']
        for saved in run['result_files'].values():
            paths.extend(Path(saved['path']).parent / name for name in saved['files'])
        hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    hashes.update({str(p.resolve()): controls.sha256(p) for p in FILES})
    requests = build_requests(design, baseline)
    return design, model, workspace, context, schema, metadata, codec, requests, hashes


def render(run):
    text = generation.render(run)
    return text.replace('# V2 full/compact generation transport pilot', '# V2 IR pilot with reasoning disabled') + (
        '\nRequest override: `reasoning_effort: none`. All other request fields match the earlier protocol-12 pair.\n'
        'This is a separate serving configuration, not a correction to the saved v1 outputs.\n'
        'The requested output budget is not a verified server capacity. Do not infer latency improvements from this single pair.\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying parent responses and preparing the fixed reasoning-none IR pair...', flush=True)
    design, model, workspace, context, schema, metadata, codec, requests, hashes = prepare()
    plan = {'case': design['case'], 'model': design['model_id'], 'configuration': design['configuration_id'],
            'conditions': list(requests), 'maximum_new_inference_requests': len(requests),
            'request_override': design['request_override'], 'requested_max_tokens_per_call': model['max_tokens'],
            'automatic_retries': 0, 'semantic_execution': False,
            'only_request_change_from_protocol_12': 'reasoning_effort=none'}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    secret = os.environ.get(model['api_key_env'])
    if not secret:
        raise ValueError('Set ' + model['api_key_env'] + ' in your terminal')
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if (run['input_fingerprint'] != controls.fingerprint(hashes) or run['requests'] != requests
                or run['model_config'] != model or run['design'] != design):
            raise ValueError('Pilot design/code/inputs changed; cannot resume')
        generation.verify_completed(run)
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_reasoning_generation__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
               'design': design, 'case': design['case'], 'model_id': design['configuration_id'],
               'base_model_id': design['model_id'], 'model_config': model,
               'requests': generation.transport.sanitize(requests, secret), 'metadata': metadata,
               'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
               'plan': plan, 'results': {}, 'result_files': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        controls.write_json(output / 'compact_output.schema.json', codec.schema)
        controls.write_json(output / 'compact_slots.json', codec.columns)
        controls.write_json(output / 'full_output.schema.json', schema)
        for path in FILES:
            target = output / 'implementation' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    run['status'] = 'running'
    controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS), str(generation.TESTS),
                            str(ROOT / 'tests/unit/test_v2_reasoning_probe.py')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        print('verification_failed: ' + str(output / 'verification.txt'), flush=True)
        return 1
    for condition, request in requests.items():
        if condition in run['results']:
            continue
        parent.verify_hashes(output, run)
        # Reuse the immutable runner's at-most-once dispatch and raw response retention.
        attempt = output / 'cells' / condition
        row = generation.run_cell(attempt, condition, request, model, secret, codec, schema, workspace, context)
        run['results'][condition] = row
        run['result_files'][condition] = generation.output_checkpoint(attempt)
        controls.write_json(output / 'run.json', run)
        (output / 'summary.md').write_text(render(run))
        print(condition + ': ' + row['status'], flush=True)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    errors = any(r['status'] in ('inference_error', 'interrupted_outcome_unknown') for r in run['results'].values())
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if errors else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
