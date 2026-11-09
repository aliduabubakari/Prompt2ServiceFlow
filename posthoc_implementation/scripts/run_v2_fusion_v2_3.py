#!/usr/bin/env python3
"""New public-input/diagnostic condition; user-run inference only."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src')); sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_fusion_v2_2 as previous
import fusion_public_tools_v2_3 as public
import fusion_public_inputs_v2_3 as inputs

# Reexecute the frozen templates into separate namespaces. Neither imported
# v2.2 controller globals nor any source file from an earlier freeze is edited.
module = public.clone_module(previous.frozen_v2_1, '_p2sf_relational_v2_3_family')
runner = public.clone_module(module.previous, '_p2sf_relational_v2_3_runner')
bridge = public.clone_module(module.previous.bridge, '_p2sf_relational_v2_3_bridge')
module.runner, module.bridge, module.public = runner, bridge, public
runner.bridge, runner.public, bridge.public = bridge, public, public
controls, replay, generation, parent = module.controls, module.replay, module.generation, module.parent
CONFIG = ROOT / 'audit/v2/semantic_fusion.v2_3.json'
FREEZE = ROOT / 'audit/v2/freeze.semantic-fusion.v2_3.json'
TESTS = ROOT / 'tests/unit/test_v2_fusion_v2_3.py'
DOC = ROOT / 'audit/v2/SEMANTIC_FUSION_V2_3.md'
for target in (module, runner):
    target.CONFIG, target.FREEZE, target.TESTS, target.DOC = CONFIG, FREEZE, TESTS, DOC
family_prepare = module.prepare
old_workspace_for, old_agent = runner.workspace_for, bridge.agent_module


def prepare(check_freeze=True):
    p = family_prepare(False)
    source = ROOT / p['design']['diagnosed_run']
    completed = replay.read_json(source / 'run.json')
    if completed['status'] != 'complete' or completed.get('invalid_cells') != 0 or completed['freeze']['freeze_id'] != 'p2sf-semantic-relational-v2.2':
        raise ValueError('Expected the completed valid v2.2 diagnostic source')
    saved = parent.verify_hashes(source, completed); generation.verify_completed(completed)
    for name, digest in saved.items():
        if name in p['hashes'] and p['hashes'][name] != digest: raise ValueError('Prior evidence changed')
        p['hashes'][name] = digest
    overlay, index = inputs.catalog_overlay(p['source_workspace'], public.input_constraints())
    p['catalog_overlay'] = overlay
    p['contract']['metadata']['catalog_snapshot']['version'] = index['version']
    p['contract']['metadata']['catalog_snapshot']['sha256'] = inputs.sha(overlay['catalog/catalog.yaml'])
    p['contract']['execution_input_constraints'] = public.input_constraints()
    p['contract']['public_information_files'] = [inputs.CONTEXT, inputs.INTERFACES]
    p['contract']['catalog_overlay'] = {name: inputs.sha(data) for name, data in overlay.items()}
    paths = [Path(__file__).resolve(), CONFIG, TESTS, DOC, Path(public.__file__), Path(inputs.__file__),
             ROOT / 'scripts/audit_v2_fusion_feedback.py',
             source / 'run.json', source / 'input_sha256.json']
    for entry in completed['result_files'].values():
        paths.extend(Path(entry['path']).parent / name for name in entry['files'])
    for path in paths: p['hashes'][str(path.resolve())] = controls.sha256(path)
    if check_freeze:
        frozen = replay.read_json(FREEZE)
        if (frozen.get('status') != 'frozen' or frozen['input_fingerprint'] != controls.fingerprint(p['hashes'])
                or frozen['design'] != p['design'] or frozen['contract'] != p['contract']):
            raise ValueError('V2.3 code, public inputs or evidence differs from its freeze')
        p['freeze'] = frozen; p['hashes'][str(FREEZE.resolve())] = controls.sha256(FREEZE)
    return p


def workspace_for(prepared, destination):
    workspace = old_workspace_for(prepared, destination)
    for relative, data in prepared['catalog_overlay'].items(): (workspace / relative).write_bytes(data)
    manifest = controls.load(workspace / 'workspace.yaml')
    manifest['catalog']['version'] = prepared['contract']['metadata']['catalog_snapshot']['version']
    manifest['catalog']['sanitized_catalog_yaml_sha256'] = prepared['contract']['metadata']['catalog_snapshot']['sha256']
    sizes = inputs.write_bundles(workspace, prepared['contract'])
    manifest['public_information_bundles'] = sizes
    manifest['files'] = [{'path': p.relative_to(workspace).as_posix(), 'sha256': controls.sha256(p)}
                         for p in sorted(workspace.rglob('*')) if p.is_file() and p.name != 'workspace.yaml']
    (workspace / 'workspace.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return workspace


def agent_module(decoding=None):
    result = old_agent(decoding)
    result.AGENT_IMAGE_TAG, result.PROXY_IMAGE_TAG = 'p2sf-v2-relational-agent', 'p2sf-v2-relational-proxy'
    result.M5_VERSION, result.M5_PROMPT_VERSION = 'v2.28.3', 'v2.public-relational.3'
    result.prompts.PROMPT_VERSION = 'v2.public-relational.3'
    old = '- `task.md` — the pipeline requirement (read it first).'
    if result.METHOD_TEMPLATE.count(old) != 1: raise ValueError('Pi public-file instruction changed')
    result.METHOD_TEMPLATE = result.METHOD_TEMPLATE.replace(old,
        '- Read `public_context.json`, then `public_interfaces.json` first. Together they contain the task, '
        'candidate sets, v2 contract, candidate descriptors and IR schema. Original public files remain available.\n'
        '- `task.md` — the pipeline requirement (also included in `public_context.json`).', 1)
    old = 'Read `v2_contract.json` before composing.'
    if result.METHOD_TEMPLATE.count(old) != 1: raise ValueError('Shared contract instruction changed')
    result.METHOD_TEMPLATE = result.METHOD_TEMPLATE.replace(old,
        'Use the execution contract in `public_context.json` (identical to `v2_contract.json`) before composing.', 1)
    return result


def create_freeze():
    if FREEZE.exists(): raise ValueError('Freeze exists; create another version')
    p = prepare(False)
    frozen = {'freeze_id': 'p2sf-semantic-relational-v2.3', 'status': 'frozen',
        'created_at': datetime.now(timezone.utc).isoformat(), 'design': p['design'], 'contract': p['contract'],
        'family_review': p['family_review'], 'input_fingerprint': controls.fingerprint(p['hashes']),
        'controller_sources': replay.read_json(previous.FREEZE)['controller_sources'],
        'environment': controls.environment(),
        'correction': 'Required public input cardinalities, binding-local public diagnostics and bounded public reading bundles. No business rules, assertion predicates, completion rules or budgets changed. Gate precedence retained.'}
    controls.write_json(FREEZE, frozen); return frozen


bridge.agent_module = agent_module
# Original M3/M4 prompts already inline the task, candidates, candidate service
# descriptors, IR schema, artifact contracts, fixtures and this v2 contract.
# Their controllers and wording are retained; both bundles are also in every
# workspace. M5 gains no evaluator information or reference composition.
runner.workspace_for = workspace_for
runner.prepare, runner.integration_controls = prepare, module.integration_controls
runner.evaluate_submission, runner.report = module.evaluate_submission, module.report
source = inspect.getsource(module.previous.main)
for old, new in [('package_v2_methods__', 'package_v2_fusion_v2_3__'),
                 ('audit/v2/image_build/semantic_methods_v2_1', 'audit/v2/image_build/semantic_fusion_v2_3')]:
    if source.count(old) != 1: raise ValueError('Parent orchestration changed')
    source = source.replace(old, new, 1)
exec(compile(source, str(Path(__file__).resolve()), 'exec'), runner.__dict__)
main = runner.main


if __name__ == '__main__': raise SystemExit(main())
