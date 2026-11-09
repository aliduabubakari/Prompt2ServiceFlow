#!/usr/bin/env python3
"""Add the declared DeepSeek cells, retaining all completed Qwen outcomes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import continue_v2_fusion_qwen_seeds as qwen

frozen, ROOT = qwen.frozen, qwen.ROOT
SCRIPT = Path(__file__).resolve()
MANIFEST = ROOT / 'audit/v2/continuation.semantic-fusion.v2_3.deepseek.json'
TESTS = ROOT / 'tests/unit/test_v2_fusion_deepseek_continuation.py'
DOC = ROOT / 'audit/v2/SEMANTIC_FUSION_DEEPSEEK_CONTINUATION.md'
SOURCE = ROOT / 'audit/outputs/package_v2_fusion_v2_3_qwen_seeds__20261026T134856Z__e91d27c3'
MODEL = 'deepinfra-deepseek-v4-1-flash'
PREFIX = 'package_v2_fusion_v2_3_deepseek__'

# Reuse the tested dispatch/resume/locking protocol in a fresh namespace.
# No edits to either prior continuation or the frozen method implementation.
module = frozen.public.clone_module(qwen, '_p2sf_v2_3_deepseek_continuation')
module.SCRIPT, module.MANIFEST, module.TESTS = SCRIPT, MANIFEST, TESTS
module.DOC, module.SOURCE, module.PREFIX = DOC, SOURCE, PREFIX
key = module.key


def prepare_qwen():
    # The v2.3 freeze dynamically inventories imports. This new orchestration
    # file is pinned below, not inserted into the old method freeze. The Qwen
    # preparation independently handles and verifies its own entry point.
    inventory = frozen.runner.implementation_files
    def without_new_entry(): return [p for p in inventory() if p.resolve() != SCRIPT]
    frozen.runner.implementation_files = without_new_entry
    try: return qwen.prepare()
    finally: frozen.runner.implementation_files = inventory


def make_spec(prepared, source):
    design = prepared['design']
    retained = [[design['pilot_model'], method, seed]
                for seed in design['seeds'] for method in design['methods']]
    if (source['cells'] != retained or source['freeze'] != prepared['freeze']
            or source['status'] not in ('complete', 'complete_with_invalid_observations')
            or source.get('source_inputs_unchanged') is not True or source['controls_only'] is not False):
        raise ValueError('Expected the completed unchanged nine-cell Qwen continuation')
    if set(source['result_files']) != {'controls', *(key(c) for c in retained)}:
        raise ValueError('Qwen source has missing or undeclared checkpoints')
    if (MODEL not in design['models'] or MODEL not in prepared['models']
            or design['methods'] != ['m3', 'm4', 'm5'] or design['seeds'] != [101, 202, 303]):
        raise ValueError('DeepSeek model/methods/seeds differ from the original declared design')
    new = [[MODEL, method, seed] for seed in design['seeds'] for method in design['methods']]
    if len(retained) != 9 or len(new) != 9 or set(map(key, retained)) & set(map(key, new)):
        raise ValueError('Expected nine disjoint retained/new cells')
    return {'continuation_id': 'p2sf-relational-v2.3-deepseek/1',
        'method_freeze_id': prepared['freeze']['freeze_id'],
        'method_freeze_sha256': frozen.controls.sha256(frozen.FREEZE),
        'source_directory': str(SOURCE), 'source_run_sha256': frozen.controls.sha256(SOURCE / 'run.json'),
        'source_input_index_sha256': frozen.controls.sha256(SOURCE / 'input_sha256.json'),
        'qwen_manifest_sha256': frozen.controls.sha256(qwen.MANIFEST),
        'model': MODEL, 'case': design['case'], 'cells': retained + new,
        'retained_cells': retained, 'new_cells': new, 'images': source['images'],
        'implementation_sha256': {str(p): frozen.controls.sha256(p) for p in (SCRIPT, TESTS, DOC)},
        'interpretation': 'Declared second-model development comparison after Qwen review. Preserve all Qwen outcomes, DeepSeek non-passes and invalid attempts. One task; no held-out validation, corpus-wide claim or submitted-score replacement.'}


def prepare(check_manifest=True):
    prepared = prepare_qwen()
    source = frozen.replay.read_json(SOURCE / 'run.json')
    qwen.verify_run(source, prepared)
    frozen.parent.verify_hashes(SOURCE, source)
    spec = make_spec(prepared, source)
    prepared['continuation'], prepared['source_run'] = spec, source
    if check_manifest:
        manifest = frozen.replay.read_json(MANIFEST)
        if manifest.get('status') != 'frozen' or manifest.get('specification') != spec:
            raise ValueError('DeepSeek continuation implementation, design or source differs from its manifest')
        prepared['continuation_manifest'] = manifest
    prepared['hashes'] = {**prepared['hashes'], **spec['implementation_sha256'],
        str(SOURCE / 'run.json'): spec['source_run_sha256'],
        str(SOURCE / 'input_sha256.json'): spec['source_input_index_sha256']}
    if check_manifest: prepared['hashes'][str(MANIFEST)] = frozen.controls.sha256(MANIFEST)
    return prepared


def write_report(output, run):
    frozen.runner.report(output, run)
    spec = run['continuation_manifest']['specification']
    rows = {k: frozen.replay.read_json(Path(v['path'])) for k, v in run['result_files'].items() if k != 'controls'}
    models = list(dict.fromkeys(c[0] for c in spec['cells']))
    methods = list(dict.fromkeys(c[1] for c in spec['cells']))
    retained = {key(c) for c in spec['retained_cells']}
    lines = ['', '## Two-model development comparison', '',
        'All nine Qwen observations are retained once, including every non-pass.',
        'Only the nine DeepSeek observations are new. Public inputs, method controllers, budgets, runtime, assertions and Docker images are unchanged.',
        'The original model roster supplies model-specific context and reasoning declarations; these are retained, not newly tuned.',
        'Three requested seeds per model/method on one development task; no independent held-out validation or corpus-wide semantic rate.', '',
        '| Model | Method | Declared | Recorded | Invalid | Public passes | All business checks pass | Mean tokens |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for model in models:
        for method in methods:
            declared = [c for c in spec['cells'] if c[0] == model and c[1] == method]
            relevant = [rows[key(c)] for c in declared if key(c) in rows]
            tokens = [r.get('usage', {}).get('total_tokens') for r in relevant]
            measured = [v for v in tokens if isinstance(v, (int, float))]
            mean = f'{sum(measured)/len(measured):.0f}' if measured else '-'
            lines.append(f"| {model} | {method} | {len(declared)} | {len(relevant)} | "
                f"{sum(r['validity'] != 'valid' for r in relevant)} | "
                f"{sum(r['validity'] == 'valid' and r['evaluation'].get('public_overall') == 'pass' for r in relevant)} | "
                f"{sum(r['validity'] == 'valid' and r['evaluation'].get('business_pass') is True for r in relevant)} | {mean} |")
    def token_total(in_retained):
        return sum(r.get('usage', {}).get('total_tokens', 0) or 0 for k, r in rows.items() if (k in retained) == in_retained)
    lines += ['', f'Retained Qwen tokens: {token_total(True)}.', f'New DeepSeek attempt tokens: {token_total(False)}.',
        'Token means use reported usage, including measured usage of invalid attempts when available; they are not billed-cost estimates.',
        'Not-evaluated valid submissions remain non-passes; invalid attempts remain in coverage.',
        'The six positive variations and three expected rejections are repeated checks within each composition, not nine tasks.',
        f"Qwen source continuation: {spec['source_directory']}",
        'Keep that directory and its source pilot when moving or archiving these referenced raw outputs. Count each cell once.', '']
    with (output / 'summary.md').open('a') as handle: handle.write('\n'.join(lines))


module.prepare, module.write_report = prepare, write_report
create_manifest, execute_pending, verify_run = module.create_manifest, module.execute_pending, module.verify_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying frozen v2.3 methods, all Qwen cells and the DeepSeek continuation manifest...', flush=True)
    prepared = prepare()
    if args.dry_run:
        spec = prepared['continuation']
        print(json.dumps({k: spec[k] for k in ('case', 'model', 'retained_cells', 'new_cells', 'method_freeze_id')}, indent=2))
        print('Retained Qwen: 9; new DeepSeek: 9; total: 18 cells. Dry-run model calls: 0.')
        return 0
    lock = ROOT / 'audit/outputs/.fusion-v2_3-deepseek-continuation.lock'
    with lock.open('a') as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('A DeepSeek continuation is already running') from None
        return module.run_locked(args, prepared)


if __name__ == '__main__': raise SystemExit(main())
