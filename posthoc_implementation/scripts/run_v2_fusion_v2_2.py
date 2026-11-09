#!/usr/bin/env python3
"""Versioned publisher-path correction; preserve failed v2.1 evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src')); sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_fusion_experiment as frozen_v2_1
import fusion_public_tools_v2_2 as public

module = public.clone_module(frozen_v2_1, '_p2sf_relational_v2_2_runner')
controls, replay, generation, parent = module.controls, module.replay, module.generation, module.parent
CONFIG = ROOT / 'audit/v2/semantic_fusion.v2_2.json'
FREEZE = ROOT / 'audit/v2/freeze.semantic-fusion.v2_2.json'
TESTS = ROOT / 'tests/unit/test_v2_fusion_v2_2.py'
DOC = ROOT / 'audit/v2/SEMANTIC_FUSION_V2_2.md'
module.CONFIG, module.FREEZE, module.TESTS, module.DOC = CONFIG, FREEZE, TESTS, DOC
module.public = public
runner = module.runner
runner.CONFIG, runner.FREEZE, runner.TESTS, runner.DOC, runner.public = CONFIG, FREEZE, TESTS, DOC, public
module.bridge.public = public
parent_prepare = module.prepare


def prepare(check_freeze=True):
    p = parent_prepare(False)
    root = ROOT / p['design']['failed_controls']
    failed = replay.read_json(root / 'run.json')
    if failed['status'] != 'control_gate_failed_no_inference' or failed['controls_only'] is not True or set(failed['result_files']) != {'controls'}:
        raise ValueError('Expected unchanged failed control-only v2.1 run')
    prior_hashes = parent.verify_hashes(root, failed); generation.verify_completed(failed)
    report = replay.read_json(root / 'controls/evaluation/public_validation.json')
    statuses = {g['gate']: g['status'] for g in report['gates']}
    if any(statuses.get('G' + str(i)) != 'pass' for i in range(6)) or statuses.get('G6-Exec') != 'fail':
        raise ValueError('Failed parent gate pattern differs; review diagnosis')
    for name, digest in prior_hashes.items():
        if name in p['hashes'] and p['hashes'][name] != digest: raise ValueError('Source evidence conflicts')
        p['hashes'][name] = digest
    paths = [Path(__file__).resolve(), CONFIG, TESTS, DOC, root / 'run.json', root / 'input_sha256.json']
    for saved in failed['result_files'].values(): paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    for path in paths: p['hashes'][str(path.resolve())] = controls.sha256(path)
    if check_freeze:
        freeze = replay.read_json(FREEZE)
        if freeze.get('status') != 'frozen' or freeze['input_fingerprint'] != controls.fingerprint(p['hashes']) or freeze['design'] != p['design'] or freeze['contract'] != p['contract']:
            raise ValueError('V2.2 implementation, design or evidence changed')
        p['freeze'] = freeze; p['hashes'][str(FREEZE.resolve())] = controls.sha256(FREEZE)
    return p


def create_freeze():
    if FREEZE.exists(): raise ValueError('Freeze exists; create another version')
    p = prepare(False)
    freeze = {'freeze_id': 'p2sf-semantic-relational-v2.2', 'status': 'frozen',
        'created_at': datetime.now(timezone.utc).isoformat(), 'design': p['design'], 'contract': p['contract'],
        'family_review': p['family_review'], 'input_fingerprint': controls.fingerprint(p['hashes']),
        'controller_sources': frozen_v2_1.replay.read_json(frozen_v2_1.FREEZE)['controller_sources'],
        'environment': controls.environment(), 'correction': 'Canonical publisher workspace root and public failure stderr; assertions/data/algorithms unchanged.'}
    controls.write_json(FREEZE, freeze); return freeze


def agent_module(decoding=None):
    result = module.old_agent(decoding)
    result.AGENT_IMAGE_TAG, result.PROXY_IMAGE_TAG = 'p2sf-v2-relational-agent', 'p2sf-v2-relational-proxy'
    result.M5_VERSION = 'v2.28.2'; result.M5_PROMPT_VERSION = 'v2.public-relational.2'
    result.prompts.PROMPT_VERSION = 'v2.public-relational.2'
    return result


module.bridge.agent_module = agent_module
module.prepare, runner.prepare = prepare, prepare
# Use the original orchestration template, with distinct paths/tags. No method
# controller logic, selection, feedback budget or evaluation predicate changes.
source = inspect.getsource(module.previous.main)
for old, new in [('package_v2_methods__', 'package_v2_fusion_v2_2__'),
                 ('audit/v2/image_build/semantic_methods_v2_1', 'audit/v2/image_build/semantic_fusion_v2_2')]:
    if source.count(old) != 1: raise ValueError('Parent orchestration changed')
    source = source.replace(old, new)
exec(compile(source, str(Path(__file__).resolve()), 'exec'), runner.__dict__)
main = runner.main


if __name__ == '__main__': raise SystemExit(main())
