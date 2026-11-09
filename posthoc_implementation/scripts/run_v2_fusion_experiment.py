#!/usr/bin/env python3
"""Second-family controls and actual M3/M4/Pi-M5; user-run inference only."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src')); sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_method_experiment as previous
import fusion_public_tools as public
import fusion_controls
import fusion_oracle as oracle

controls, replay, generation, parent = previous.controls, previous.replay, previous.generation, previous.parent
CONFIG = ROOT / 'audit/v2/semantic_fusion.json'
FREEZE = ROOT / 'audit/v2/freeze.semantic-fusion.v2.json'
TESTS = ROOT / 'tests/unit/test_v2_fusion.py'
DOC = ROOT / 'audit/v2/SEMANTIC_FUSION_EXPERIMENT.md'
runner = public.clone_module(previous, '_p2sf_relational_method_runner')
runner.public = public
runner.CONFIG, runner.FREEZE, runner.TESTS, runner.DOC = CONFIG, FREEZE, TESTS, DOC
bridge = public.clone_module(previous.bridge, '_p2sf_relational_method_bridge')
bridge.public = public
old_agent = bridge.agent_module


def agent_module(decoding=None):
    module = old_agent(decoding)
    module.AGENT_IMAGE_TAG, module.PROXY_IMAGE_TAG = 'p2sf-v2-relational-agent', 'p2sf-v2-relational-proxy'
    module.M5_VERSION = 'v2.28.1'
    module.M5_PROMPT_VERSION = 'v2.public-relational.1'
    module.prompts.PROMPT_VERSION = 'v2.public-relational.1'
    return module


bridge.agent_module = agent_module
runner.bridge = bridge
# Only orchestration labels/build paths change here, not the method controllers.
# Guard the exact inherited literals so a future source change cannot silently
# alter the versioned runner being adapted.
source = inspect.getsource(previous.main)
for old, new in [('package_v2_methods__', 'package_v2_fusion__'),
                 ('audit/v2/image_build/semantic_methods_v2_1', 'audit/v2/image_build/semantic_fusion_v2_1')]:
    if source.count(old) != 1: raise ValueError('Parent orchestration changed; review family adapter')
    source = source.replace(old, new)
exec(compile(source, str(Path(__file__).resolve()), 'exec'), runner.__dict__)


def projection():
    return {'projection_contract_version': 'p2sf.public-relational-projections/1', 'profile_version': 'relational-routing-1',
        'rules': [{'service_id': 'api_table_output_bundle_publisher', 'service_version': '1.0.0', 'operation_profile': 'publish_outputs',
            'port': 'output_artifacts', 'artifact_role': 'report', 'artifact_data_types': ['json', 'object'],
            'projection': 'publication_audit_manifest', 'maximum_auxiliary_reports': 1,
            'require_declared_intent_output': True, 'require_no_consumers': True}]}


def prepare(check_freeze=True):
    d = replay.read_json(CONFIG)
    if d['methods'] != ['m3', 'm4', 'm5'] or d['repair_budget'] != 3 or d['validator_budget'] != 4 or d['m5_step_budget'] != 12:
        raise ValueError('Inherited controller budgets changed')
    root = ROOT / d['parent_methods']; completed = replay.read_json(root / 'run.json')
    if completed['status'] != 'complete' or completed.get('source_inputs_unchanged') is not True: raise ValueError('Completed unchanged parent method experiment required')
    hashes = parent.verify_hashes(root, completed); generation.verify_completed(completed)
    census = ROOT / d['selection_census']
    families = replay.read_json(census / 'reference_families.json')
    selected = next(f for f in families if f['family_id'] == d['selected_family'])
    if selected['rank'] != 1 or selected['reference_cases'] != d['reviewed_family_cases'] or sorted(selected['services']) != sorted(s + '@1.0.0' for s in public.backend.OPERATIONS):
        raise ValueError('Reference-only family selection differs')
    inventory = replay.read_json(ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json')
    baseline = Path(inventory['control_directory']) / 'cases'
    review = []
    for case in selected['reference_cases']:
        workspace = baseline / case / 'public_workspace' / case
        generation.census.public_context(workspace)
        nominal = workspace / 'fixtures/scenarios/nominal'
        manifest = replay.read_json(nominal / 'fixture.json')
        paths = [oracle.path_at(nominal, name) for name in manifest['inputs'].values()]
        complete = len(paths) == 3 and all(p.is_file() for p in paths)
        review.append({'case': case, 'manifest_roles': sorted(manifest['inputs']), 'public_sources_complete': complete,
                       'state': 'eligible_for_clarified_contract' if complete else 'reference_source_role_requires_clarification',
                       'task_sha256': controls.sha256(workspace / 'task.md')})
    eligible = [r['case'] for r in review if r['public_sources_complete']]
    if eligible != [d['case']]: raise ValueError('Public input completeness selection changed')
    workspace = baseline / d['case'] / 'public_workspace' / d['case']
    metadata = generation.public_metadata(workspace, controls.load(workspace / 'workspace.yaml'), d)
    profile = replay.read_json(ROOT / d['profile_file']); public.backend.verify_profile(profile)
    manifest = replay.read_json(workspace / 'fixtures/scenarios/nominal/fixture.json')
    if not all(key in manifest['inputs'] for key in profile['inputs'].values()): raise ValueError('Missing declared public input role')
    contract = {'version': public.VERSION, 'metadata': metadata, 'profile': profile, 'projection': projection(),
        'assembly_policy': replay.read_json(ROOT / 'audit/v2/assembly_policy.json'),
        'registered_operations': [{'service_id': service, 'service_version': '1.0.0', 'operation_profile': op[0]} for service, op in public.backend.OPERATIONS.items()],
        'input_role': {'fixture_ref': 'fixtures/inputs/fixture.json'},
        'public_fixture_previews': bridge.original_prompts.load_fixture_previews(workspace), 'rules': (ROOT / d['public_rules']).read_text()}
    models = previous.load_model_configs(ROOT / d['models_file'])
    paths = [*runner.implementation_files(), Path(__file__).resolve(), CONFIG, DOC, TESTS, ROOT / d['profile_file'], ROOT / d['public_rules'],
             ROOT / d['models_file'], root / 'run.json', root / 'input_sha256.json', census / 'reference_families.json']
    for saved in completed['result_files'].values(): paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    for case in d['reviewed_family_cases']:
        w = baseline / case / 'public_workspace' / case
        paths.extend(p for p in w.rglob('*') if p.is_file())
    for path in paths:
        name, digest = str(path.resolve()), controls.sha256(path)
        if name in hashes and hashes[name] != digest: raise ValueError('Pinned family evidence changed: ' + name)
        hashes[name] = digest
    prepared = {'design': d, 'hashes': hashes, 'source_workspace': workspace, 'contract': contract,
                'models': models, 'family_review': review}
    if check_freeze:
        frozen = replay.read_json(FREEZE)
        if frozen.get('status') != 'frozen' or frozen['input_fingerprint'] != controls.fingerprint(hashes) or frozen['contract'] != contract or frozen['design'] != d or frozen['family_review'] != review:
            raise ValueError('Frozen relational code, public contract or evidence changed')
        prepared['freeze'] = frozen; hashes[str(FREEZE.resolve())] = controls.sha256(FREEZE)
    return prepared


def create_freeze():
    if FREEZE.exists(): raise ValueError('Freeze already exists; create a new version')
    p = prepare(False)
    freeze = {'freeze_id': 'p2sf-semantic-relational-v2.1', 'status': 'frozen', 'created_at': datetime.now(timezone.utc).isoformat(),
        'design': p['design'], 'contract': p['contract'], 'family_review': p['family_review'],
        'input_fingerprint': controls.fingerprint(p['hashes']), 'environment': controls.environment(),
        'controller_sources': {name: controls.sha256(Path(m.__file__)) for name, m in
            [('methods', bridge.original_methods), ('prompts', bridge.original_prompts), ('pi_wrapper', bridge.original_agentic)]}}
    controls.write_json(FREEZE, freeze); return freeze


def evaluate_submission(prepared, workspace, submission, attempt):
    attempt.mkdir(parents=True, exist_ok=False)
    try: public.compile_submission(workspace, submission)
    except Exception as exc: controls.write_json(attempt / 'compile_error.json', {'error': str(exc)})
    report = public.validate_submission(workspace, submission)
    controls.write_json(attempt / 'public_validation.json', report)
    row = {'public_overall': report['overall_status'], 'first_failing_gate': report['first_failing_gate'], 'state': 'blocked_public_gates', 'evaluated': False, 'business_pass': None}
    if report['overall_status'] != 'pass':
        controls.write_json(attempt / 'result.json', row); return row
    ir = controls.load(submission / 'serviceflow.yaml')
    controls.write_json(attempt / 'committed_ir.json', ir)
    committed = controls.sha256(attempt / 'committed_ir.json')
    d = prepared['design']; instance = attempt / 'instance'
    shutil.copytree(submission / 'runtime', instance / 'runtime')
    fusion_controls.input_bank(prepared['source_workspace'] / 'fixtures/scenarios/nominal', instance / 'fixtures', prepared['contract']['profile'], d)
    manifest = controls.load(instance / 'runtime/manifest.yaml')
    manifest['scenarios'] = [{'name': n, 'parameters': {}, 'fixture_root': 'fixtures/scenarios/' + n} for n in d['positive_scenarios'] + d['rejection_scenarios']]
    (instance / 'runtime/manifest.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    raw = controls._execute_scenarios(instance, manifest, sandbox_generated=True)
    controls.persist_snapshots(raw, attempt / 'execution')
    if {r['scenario'] for r in raw} != {s['name'] for s in manifest['scenarios']}: raise ValueError('Incomplete private scenario roster')
    schemas = previous.prior.pilot.integration.prior.real.base.schemas_for(ir, workspace)
    from jsonschema import Draft202012Validator
    checks = {}
    for result in raw:
        checked = oracle.check(result, ir, instance / 'fixtures/scenarios' / result['scenario'], prepared['contract']['profile'], d['rejection_reasons'])
        for identity, schema in schemas.items():
            name = 'artifacts/' + identity + '.json'
            if name not in result['_snapshot']: continue
            try: Draft202012Validator(schema).validate(json.loads(result['_snapshot'][name])); passed = True
            except Exception: passed = False
            checked['checks'].append({'check': 'artifact_schema:' + identity, 'pass': passed})
            checked['pass'] &= passed
        checks[result['scenario']] = checked
    row.update(state='evaluated', evaluated=True, scenarios=checks, business_pass=all(c['pass'] for c in checks.values()),
               positive_passes=sum(checks[n]['pass'] for n in d['positive_scenarios']), correct_rejections=sum(checks[n]['pass'] for n in d['rejection_scenarios']),
               committed_ir_sha256=committed)
    if controls.sha256(attempt / 'committed_ir.json') != committed: raise ValueError('Committed IR changed')
    controls.write_json(attempt / 'result.json', row); return row


def integration_controls(prepared, directory):
    workspace = runner.workspace_for(prepared, directory / 'workspace')
    submission = workspace / 'submission'; submission.mkdir()
    ir = fusion_controls.reference_ir(prepared['contract']['metadata'], (workspace / 'task.md').read_text())
    (submission / 'serviceflow.yaml').write_text(controls.yaml.safe_dump(ir, sort_keys=False))
    controls.write_json(directory / 'family_selection.json', prepared['family_review'])
    row = evaluate_submission(prepared, workspace, submission, directory / 'evaluation')
    mutants = {}
    if row.get('business_pass') is True:
        ir = controls.load(submission / 'serviceflow.yaml')
        index = replay.read_json(directory / 'evaluation/execution/index.json')
        entry = next(e for e in index if e['scenario'] == 'nominal')
        nominal = previous.prior.pilot.integration.prior.restored(entry, directory / 'evaluation/execution')
        for defect in prepared['design']['negative_controls']:
            mutated = oracle.mutate(nominal, ir, prepared['contract']['profile'], defect)
            checked = oracle.check(mutated, ir, directory / 'evaluation/instance/fixtures/scenarios/nominal', prepared['contract']['profile'], prepared['design']['rejection_reasons'])
            mutants[defect] = {'detected': not checked['pass'], 'checks': checked['checks']}
    row['negative_controls'] = mutants
    row['control_gate_pass'] = row.get('business_pass') is True and len(mutants) == 4 and all(m['detected'] for m in mutants.values())
    controls.write_json(directory / 'result.json', row); return row


original_report = runner.report


def report(output, run):
    original_report(output, run)
    path = output / 'summary.md'
    text = path.read_text().replace('# V2 actual-method semantic experiment', '# V2 relational-family method experiment', 1)
    detail = ['## Public family coverage', '', '| Candidate task | Public-input review |', '|---|---|']
    detail.extend(f"| {row['case']} | {row['state']} |" for row in run['freeze']['family_review'])
    detail += ['', 'Only support_profile_context_join is enabled under the clarified relational-routing-1 contract.',
               'The supplied routing policy is the reference input. Subscription-plan lookup and freshness checks are not claimed.',
               'The two other family tasks require a public reference-source clarification; neither is silently filled or counted as evaluated.', '']
    path.write_text(text + '\n' + '\n'.join(detail))


runner.prepare, runner.integration_controls, runner.evaluate_submission, runner.report = prepare, integration_controls, evaluate_submission, report
main = runner.main


if __name__ == '__main__': raise SystemExit(main())
