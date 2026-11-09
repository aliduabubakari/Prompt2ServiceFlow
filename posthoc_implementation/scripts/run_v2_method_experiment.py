#!/usr/bin/env python3
"""User-run v2 experiment: actual M3/M4/Pi-M5 and shared real service tools."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_resolution as prior
import semantic_public_tools as public
import semantic_method_bridge as bridge
from prompt2serviceflow.experiments.llm import ModelConfig, UsageLedger, CompletionResult, LLMError, load_model_configs

generation, controls, replay, parent = prior.generation, prior.controls, prior.replay, prior.parent
CONFIG = ROOT / 'audit/v2/semantic_methods.json'
FREEZE = ROOT / 'audit/v2/freeze.semantic-methods.v2.json'
TESTS = ROOT / 'tests/unit/test_v2_semantic_methods.py'
DOC = ROOT / 'audit/v2/SEMANTIC_METHOD_EXPERIMENT.md'


def implementation_files():
    paths = {Path(__file__).resolve(), CONFIG, TESTS, DOC}
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and '.venv' not in path.parts and 'tests' not in path.relative_to(ROOT).parts and path.is_file():
                paths.add(path)
    for name in ('agent_driver.mjs', 'proxy.py'):
        paths.add(ROOT / 'experiments/m5' / name)
    return sorted(paths)


def prepare(check_freeze=True):
    design = replay.read_json(CONFIG)
    if design['methods'] != ['m3', 'm4', 'm5'] or design['validator_budget'] != design['repair_budget'] + 1 or design['max_workers'] != 1:
        raise ValueError('Unsupported method/budget design')
    root = ROOT / design['parent_replay']
    completed = replay.read_json(root / 'run.json')
    if completed['status'] != 'complete' or completed.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged corpus replay required')
    hashes = parent.verify_hashes(root, completed)
    generation.verify_completed(completed)
    validated_root = ROOT / design['validated_resolution']
    validated = replay.read_json(validated_root / 'run.json')
    generation.verify_completed(validated)
    if validated.get('source_inputs_unchanged') is not True or validated['outcome'].get('profile_all_controls_pass') is not True:
        raise ValueError('Validated semantic development composition required')
    source_root = ROOT / validated['design']['source_pilot']
    source = replay.read_json(source_root / 'run.json')
    if source['design']['case'] != design['case']:
        raise ValueError('Only the reviewed task/profile association is enabled')
    fixtures = source_root / 'evaluation_fixtures'
    if prior.pilot.file_hashes(fixtures) != source['evaluation_fixture_files']:
        raise ValueError('Verified evaluation fixture bank changed')
    for key in ('positive_scenarios', 'rejection_scenarios'):
        if design[key] != source['design'][key]: raise ValueError('Scenario roster changed')
    inventory = replay.read_json(ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json')
    workspace = Path(inventory['control_directory']) / 'cases' / design['case'] / 'public_workspace' / design['case']
    manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, manifest)
    metadata = generation.public_metadata(workspace, manifest, design)
    base = completed['freeze']['design']
    profile = replay.read_json(ROOT / base['profile'])
    public.backend.verify_profile(profile)
    matches = prior.pilot.integration.prior.real.repairer.manifests(workspace / 'fixtures/scenarios/nominal', profile)
    if len(matches) != 1: raise ValueError('Unique public input manifest required')
    contract = {'version': public.VERSION, 'metadata': metadata, 'profile': profile,
        'projection': replay.read_json(ROOT / base['projection_contract']),
        'assembly_policy': replay.read_json(ROOT / base['assembly_policy']),
        'registered_operations': [{'service_id': s, 'service_version': '1.0.0', 'operation_profile': v[0]}
                                  for s, v in sorted(public.backend.window.OPERATIONS.items())],
        'input_role': {'fixture_ref': 'fixtures/inputs/' + matches[0]},
        'public_fixture_previews': bridge.original_prompts.load_fixture_previews(workspace),
        'rules': (ROOT / design['public_rules']).read_text()}
    models = load_model_configs(ROOT / design['models_file'])
    if list(models) != design['models']: raise ValueError('Model roster changed')
    paths = [*implementation_files(), ROOT / design['models_file'], ROOT / design['public_rules'],
             root / 'run.json', root / 'input_sha256.json', validated_root / 'run.json',
             validated_root / 'execution_attempt/candidate_ir.json', source_root / 'run.json']
    paths.extend(workspace / f['path'] for f in manifest['files'])
    paths.extend(fixtures / name for name in source['evaluation_fixture_files'])
    for path in paths:
        identity, digest = str(path.resolve()), controls.sha256(path)
        if identity in hashes and hashes[identity] != digest: raise ValueError('Pinned implementation/input changed: ' + identity)
        hashes[identity] = digest
    prepared = dict(design=design, hashes=hashes, source_workspace=workspace, contract=contract,
                    fixtures=fixtures, models=models, control_ir=validated_root / 'execution_attempt/candidate_ir.json')
    if check_freeze:
        frozen = replay.read_json(FREEZE)
        if frozen.get('status') != 'frozen' or frozen['input_fingerprint'] != controls.fingerprint(hashes) or frozen['contract'] != contract or frozen['design'] != design:
            raise ValueError('Frozen v2 method design, implementation or inputs changed')
        prepared['freeze'] = frozen
        hashes[str(FREEZE.resolve())] = controls.sha256(FREEZE)
    return prepared


def create_freeze():
    if FREEZE.exists(): raise ValueError('Freeze exists; create a new version instead of overwriting')
    p = prepare(False)
    freeze = {'freeze_id': 'p2sf-semantic-methods-v2.1', 'status': 'frozen',
        'created_at': datetime.now(timezone.utc).isoformat(), 'design': p['design'], 'contract': p['contract'],
        'input_fingerprint': controls.fingerprint(p['hashes']),
        'public_runtime_tool_version': public.VERSION,
        'controller_sources': {name: controls.sha256(Path(module.__file__)) for name, module in
            [('methods', bridge.original_methods), ('prompts', bridge.original_prompts), ('pi_wrapper', bridge.original_agentic)]},
        'environment': controls.environment(), 'scope': p['design']['scope']}
    controls.write_json(FREEZE, freeze)
    return freeze


def workspace_for(prepared, destination):
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('task.md', 'candidates', 'catalog', 'contracts', 'schemas', 'fixtures'):
        source = prepared['source_workspace'] / name
        if source.is_dir(): shutil.copytree(source, destination / name)
        else: shutil.copy2(source, destination / name)
    controls.write_json(destination / public.CONTRACT, prepared['contract'])
    # Only these public tool entry points are added; no evaluator, reference
    # IR, altered-input bank, API credential or prior result is staged.
    bins = destination / 'bin'; bins.mkdir()
    for name, action in [('compile', 'compile'), ('validate_submission', 'validate')]:
        path = bins / name
        path.write_text('#!/usr/bin/env python3\nimport sys\nsys.path.insert(0,"/opt/p2sf/v2")\n'
            'from semantic_public_tools import main\nraise SystemExit(main([' + repr(action) + ',*sys.argv[1:]]))\n')
        path.chmod(0o755)
    manifest = controls.load(prepared['source_workspace'] / 'workspace.yaml')
    manifest['files'] = [{'path': p.relative_to(destination).as_posix(), 'sha256': controls.sha256(p)}
                         for p in sorted(destination.rglob('*')) if p.is_file()]
    (destination / 'workspace.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return destination


def evaluate_submission(prepared, workspace, submission, attempt):
    attempt.mkdir(parents=True, exist_ok=False)
    try:
        public.compile_submission(workspace, submission)
    except Exception as exc:
        controls.write_json(attempt / 'compile_error.json', {'error': str(exc)})
    report = public.validate_submission(workspace, submission)
    controls.write_json(attempt / 'public_validation.json', report)
    row = {'public_overall': report['overall_status'], 'first_failing_gate': report['first_failing_gate'],
           'state': 'blocked_public_gates', 'evaluated': False, 'business_pass': None}
    if report['overall_status'] != 'pass':
        controls.write_json(attempt / 'result.json', row)
        return row
    ir = controls.load(submission / 'serviceflow.yaml')
    controls.write_json(attempt / 'committed_ir.json', ir)
    row['committed_ir_sha256'] = controls.sha256(attempt / 'committed_ir.json')
    instance = attempt / 'instance'
    shutil.copytree(submission / 'runtime', instance / 'runtime')
    shutil.copytree(prepared['fixtures'], instance / 'fixtures')
    manifest = controls.load(instance / 'runtime/manifest.yaml')
    design = prepared['design']
    manifest['scenarios'] = [{'name': n, 'parameters': {}, 'fixture_root': 'fixtures/scenarios/' + n}
                             for n in design['positive_scenarios'] + design['rejection_scenarios']]
    (instance / 'runtime/manifest.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    results = controls._execute_scenarios(instance, manifest, sandbox_generated=True)
    controls.persist_snapshots(results, attempt / 'execution')
    if {r['scenario'] for r in results} != {s['name'] for s in manifest['scenarios']}:
        raise ValueError('Incomplete evaluation scenario roster')
    schemas = prior.pilot.integration.prior.real.base.schemas_for(ir, workspace)
    checks = {}
    for result in results:
        fixture = prepared['fixtures'] / 'scenarios' / result['scenario']
        checked = prior.pilot.integration.evaluate(result, ir, fixture, prepared['contract']['profile'], design, schemas)
        projections = prior.pilot.integration.prior.real.oracle.check(result, ir, fixture, prepared['contract']['profile'], result['scenario'], schemas)
        checked['projection_checks'] = projections['checks']
        checked['pass'] = checked['pass'] and projections['pass']
        checks[result['scenario']] = checked
    row.update(state='evaluated', evaluated=True, scenarios=checks,
               business_pass=all(v['pass'] for v in checks.values()),
               positive_passes=sum(checks[n]['pass'] for n in design['positive_scenarios']),
               correct_rejections=sum(checks[n]['pass'] for n in design['rejection_scenarios']))
    if controls.sha256(attempt / 'committed_ir.json') != row['committed_ir_sha256']:
        raise ValueError('Committed submission changed during private evaluation')
    controls.write_json(attempt / 'result.json', row)
    return row


def integration_controls(prepared, directory):
    workspace = workspace_for(prepared, directory / 'workspace')
    submission = workspace / 'submission'; submission.mkdir()
    (submission / 'serviceflow.yaml').write_text(controls.yaml.safe_dump(replay.read_json(prepared['control_ir']), sort_keys=False))
    row = evaluate_submission(prepared, workspace, submission, directory / 'evaluation')
    mutants = {}
    if row.get('business_pass') is True:
        ir = controls.load(submission / 'serviceflow.yaml')
        index = replay.read_json(directory / 'evaluation/execution/index.json')
        entry = next(e for e in index if e['scenario'] == 'nominal')
        nominal = prior.pilot.integration.prior.restored(entry, directory / 'evaluation/execution')
        for defect in prepared['design']['negative_controls']:
            mutated = prior.pilot.integration.prior.mutate(nominal, ir, defect)
            checked = prior.pilot.integration.evaluate(mutated, ir, prepared['fixtures'] / 'scenarios/nominal',
                prepared['contract']['profile'], prepared['design'])
            mutants[defect] = {'detected': not checked['pass'], 'checks': checked['checks']}
    row['negative_controls'] = mutants
    row['control_gate_pass'] = row.get('business_pass') is True and len(mutants) == len(prepared['design']['negative_controls']) and all(v['detected'] for v in mutants.values())
    controls.write_json(directory / 'result.json', row)
    return row


class RecordingClient:
    """One SDK request per stage; retain raw final/reasoning/tool fields."""
    def __init__(self, config, ledger, directory):
        self.config, self.ledger, self.directory = config, ledger, directory
        self.calls = 0

    def complete(self, *, stage, system, user):
        self.calls += 1
        target = self.directory / f'{self.calls:03d}_{stage}'
        target.mkdir(parents=True, exist_ok=False)
        model = asdict(self.config)
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        request = generation.transport.request(model, messages)
        secret = os.environ.get(self.config.api_key_env)
        controls.write_json(target / 'request.json', generation.transport.sanitize(request, secret))
        controls.write_json(target / 'request_started.json', {'stage': stage, 'automatic_retries': 0})
        response = generation.transport.complete(model, request, secret)
        controls.write_json(target / 'response.json', response)
        observed = generation.transport.observe(response)
        controls.write_json(target / 'observation.json', observed)
        if response['status'] != 'response_received' or not isinstance(observed.get('text'), str) or observed.get('tool_calls_present'):
            raise LLMError('V2 inference/compatibility failure: ' + observed['status'])
        usage = observed.get('usage') or {}
        usage = {**usage, 'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens', 0)}
        result = CompletionResult(observed['text'], observed.get('reported_model') or self.config.model_name,
                                  observed['finish_reason'], usage, response['latency_s'])
        self.ledger.record(stage, result, self.config)
        return result


def execute_cell(prepared, model_id, method, seed, directory, skip_images):
    directory.mkdir(parents=True, exist_ok=False)
    controls.write_json(directory / 'started.json', {'model': model_id, 'method': method, 'seed': seed,
                                                   'policy': 'No automatic redispatch after interruption'})
    config = replace(prepared['models'][model_id], seed=seed)
    workspace = workspace_for(prepared, directory / 'workspace')
    submission = workspace / 'submission'
    ledger = UsageLedger()
    started = time.monotonic()
    client = None
    row = {'model': model_id, 'method': method, 'seed': seed,
           'sample_index': prepared['design']['seeds'].index(seed), 'case': prepared['design']['case'], 'validity': 'valid'}
    try:
        if method in ('m3', 'm4'):
            module = bridge.method_module(workspace)
            client = RecordingClient(config, ledger, directory / 'llm')
            if method == 'm3':
                result = module.run_m3(client, workspace, submission)
            else:
                result = module.run_m4(client, workspace, submission, repair_budget=prepared['design']['repair_budget'])
            controls.write_json(directory / 'method_result.json', asdict(result))
            row['method_status'] = result.status
            row['usage'] = ledger.summary(config)
            row['usage']['validator_calls'] = result.validator_calls
        else:
            decoding = {key: getattr(config, key) for key in ('temperature', 'top_p', 'seed', 'max_tokens')}
            module = bridge.agent_module(decoding)
            if prepared.get('expected_images') is not None and module.inspect_image_digests() != prepared['expected_images']:
                raise ValueError('M5 image identities changed after batch preflight; no M5 inference dispatched')
            manifest = module.run_m5(workspace=workspace, instance_dir=workspace, model=config, run_dir=directory / 'agent',
                validator_budget=prepared['design']['validator_budget'], token_cap=prepared['design']['m5_token_cap'],
                timeout_s=prepared['design']['m5_timeout_s'], agent_step_budget=prepared['design']['m5_step_budget'],
                max_idle_continuations=prepared['design']['m5_idle_continuations'], skip_image_build=skip_images,
                sample_index=prepared['design']['seeds'].index(seed), batch_id=directory.parents[1].name,
                roster_path=ROOT / prepared['design']['models_file'], freeze_document=prepared['freeze'])
            row['method_status'] = manifest['stopping_reason']
            row['image_digests'] = manifest['image_digests']
            if prepared.get('expected_images') is not None and manifest['image_digests'] != prepared['expected_images']:
                raise ValueError('M5 executed image identities differ from batch preflight')
            row['usage'] = manifest['usage']
            row['usage']['evaluation_validator_calls'] = max(0, row['usage'].get('evaluation_validator_calls', 0) - 1)
            row['v1_private_scorer'] = 'suppressed_not_called'
            submission = directory / 'agent/agent_workspace/submission'
            # Host evaluation uses the untouched public workspace, even if an
            # agent edited its own staged inputs or contract files.
        row['evaluation'] = evaluate_submission(prepared, workspace, submission, directory / 'evaluation')
    except (LLMError, bridge.original_agentic.M5Error) as exc:
        row.update(validity='invalid_infrastructure_or_provider', error=generation.transport.sanitize(str(exc), os.environ.get(config.api_key_env)), evaluation={'state': 'not_evaluated', 'evaluated': False})
        row.setdefault('usage', ledger.summary(config))
    except Exception as exc:
        row.update(validity='invalid_infrastructure_or_provider' if type(exc).__name__ == 'M5Error' else 'invalid_infrastructure_or_inspection',
                   error=generation.transport.sanitize(type(exc).__name__ + ': ' + str(exc), os.environ.get(config.api_key_env)),
                   evaluation={'state': 'not_evaluated', 'evaluated': False})
        row.setdefault('usage', ledger.summary(config))
    if method == 'm5' and (directory / 'agent/manifest.json').is_file():
        agent_record = replay.read_json(directory / 'agent/manifest.json')
        row['usage'] = agent_record.get('usage', row.get('usage', {}))
        row['usage']['evaluation_validator_calls'] = max(0, row['usage'].get('evaluation_validator_calls', 0) - 1)
    row['wall_time_s'] = time.monotonic() - started
    row['inference_request_attempts'] = client.calls if client is not None else None
    controls.write_json(directory / 'result.json', row)
    return row


def report(output, run):
    rows = [replay.read_json(Path(saved['path'])) for saved in run['result_files'].values() if Path(saved['path']).parent.name != 'controls']
    controls.write_json(output / 'results.json', rows)
    control = replay.read_json(output / 'controls/result.json')
    lines = ['# V2 actual-method semantic experiment', '', f"Freeze {run['freeze']['freeze_id']}; status {run['status']}.",
        'Mode: integration controls only; zero inference.' if run['controls_only'] else 'Mode: new method generation and evaluation.',
        'One supported development task. Shared public information and compiler rules. Actual M3/M4/Pi-M5 controllers.', '',
        f"Integration control gate: {control['control_gate_pass']}; public gates: {control.get('public_overall', '-')}; first failure: {control.get('first_failing_gate')}.",
        f"Control positive cases: {str(control.get('positive_passes')) + '/6' if control.get('evaluated') else 'not evaluated'}; correct rejections: {str(control.get('correct_rejections')) + '/3' if control.get('evaluated') else 'not evaluated'}; business mutants detected: {sum(v['detected'] for v in control['negative_controls'].values())}/4.",
        'The integration control is excluded from model-observation counts.', '',
        '| Model | Method | Seed | Validity | Public gate result | Positive cases | Correct rejections | Total tokens |',
        '|---|---|---:|---|---|---:|---:|---:|']
    for row in rows:
        e = row['evaluation']
        lines.append(f"| {row['model']} | {row['method']} | {row['seed']} | {row['validity']} | {e.get('public_overall','-')} | {str(e.get('positive_passes'))+'/6' if e.get('evaluated') else '-'} | {str(e.get('correct_rejections'))+'/3' if e.get('evaluated') else '-'} | {row.get('usage',{}).get('total_tokens','-')} |")
    lines += ['', 'Invalid attempts remain in coverage; blocked valid submissions are not silently dropped. A complete batch does not imply successful business outputs.',
        'Six input variations and three expected rejections are repeated checks of each composition, not nine independent pipelines. Seeds measure repeated generation; server support for decoding settings is not assumed.',
        'Business outputs are checked only after method termination. No semantic assertions or evaluation variants enter prompts or public repair feedback.',
        'The common v2 changes include explicit execution contracts, real runtime packaging, documented JSON/any compatibility and logged compiler completion. This is not an unchanged-method v1 rescore or corpus-wide result.',
        'Raw requests/responses, stages, repair history, Pi transcript/proxy wire records, public reports, compilation edits, committed IR, usage, image identities and private execution checks are retained.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--controls-only', action='store_true')
    parser.add_argument('--build-m5-images', action='store_true')
    parser.add_argument('--full-design', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying the new v2 method design and shared public execution contract...', flush=True)
    p = prepare()
    d = p['design']
    model_ids = d['models'] if args.full_design else [d['pilot_model']]
    seeds = d['seeds'] if args.full_design else [d['pilot_seed']]
    cells = [(model, method, seed) for model in model_ids for seed in seeds for method in d['methods']]
    if args.dry_run:
        print(json.dumps({'case': d['case'], 'models': model_ids, 'methods': d['methods'], 'seeds': seeds,
            'declared_cells': len(cells), 'private_cases_per_composition': 9, 'repair_budget': d['repair_budget'],
            'm5_validator_budget': d['validator_budget'], 'm5_step_budget': d['m5_step_budget'],
            'common_public_contract': public.VERSION, 'controllers': p['freeze']['controller_sources'],
            'model_calls_during_preflight': 0, 'original_scores_replaced': False}, indent=2))
        return 0
    if args.build_m5_images:
        images = bridge.agent_module().build_images(ROOT / 'audit/v2/image_build/semantic_methods_v2_1')
        print(json.dumps(images, indent=2))
        return 0
    if not args.controls_only:
        for model in model_ids:
            if not os.environ.get(p['models'][model].api_key_env):
                raise ValueError('Set ' + p['models'][model].api_key_env + ' in your terminal')
        # Discover absent images/daemon before any paid generation call.
        images = bridge.agent_module().inspect_image_digests()
    else:
        images = None
    p['expected_images'] = images
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if (run['input_fingerprint'] != controls.fingerprint(p['hashes']) or run['freeze'] != p['freeze']
                or run['cells'] != [list(c) for c in cells] or run['controls_only'] != args.controls_only or run['images'] != images):
            raise ValueError('Design, images or immutable inputs differ; cannot resume')
        generation.verify_completed(run)
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_methods__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': d['package_version'], 'audit_protocol_version': d['audit_protocol_version'],
            'freeze': p['freeze'], 'input_fingerprint': controls.fingerprint(p['hashes']),
            'cells': [list(c) for c in cells], 'controls_only': args.controls_only, 'images': images,
            'status': 'running', 'result_files': {}, 'environment': controls.environment()}
        controls.write_json(output / 'run.json', run)
        controls.write_json(output / 'input_sha256.json', p['hashes'])
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, capture_output=True, text=True, timeout=90)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode: raise ValueError('Local v2 integration verification failed; see verification.txt')
    control_dir = output / 'controls'
    if 'controls' not in run['result_files']:
        if control_dir.exists(): raise ValueError('Interrupted controls: preserve this attempt and start a new batch')
        control = integration_controls(p, control_dir)
        run['result_files']['controls'] = generation.output_checkpoint(control_dir)
        controls.write_json(output / 'run.json', run)
    control = replay.read_json(control_dir / 'result.json')
    if not control['control_gate_pass']:
        run['status'] = 'control_gate_failed_no_inference'
        controls.write_json(output / 'run.json', run); report(output, run)
        print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
        return 1
    if not args.controls_only:
        for index, (model, method, seed) in enumerate(cells):
            key = f'{model}/{method}/{seed}'
            if key in run['result_files']: continue
            directory = output / 'cells' / f'{index:03d}_{model}_{method}_{seed}'
            if directory.exists():
                # An interrupted model attempt is never automatically repeated.
                if (directory / 'result.json').is_file():
                    result = replay.read_json(directory / 'result.json')
                    if (result['model'], result['method'], result['seed'], result['case']) != (model, method, seed, d['case']):
                        raise ValueError('Uncheckpointed result identity differs')
                else:
                    result = {'model': model, 'method': method, 'seed': seed, 'case': d['case'],
                        'validity': 'invalid_interrupted_attempt', 'usage': {},
                        'evaluation': {'state': 'interrupted_unknown_no_redispatch', 'evaluated': False}}
                    controls.write_json(directory / 'result.json', result)
            else:
                result = execute_cell(p, model, method, seed, directory, True)
            run['result_files'][key] = generation.output_checkpoint(directory)
            controls.write_json(output / 'run.json', run)
            print(f"recorded {model} {method} seed={seed}: {result['validity']}, {result['evaluation']['state']}", flush=True)
    parent.verify_hashes(output, run)
    generation.verify_completed(run)
    run['source_inputs_unchanged'] = True
    finished = [replay.read_json(Path(saved['path'])) for key, saved in run['result_files'].items() if key != 'controls']
    run['invalid_cells'] = sum(r['validity'] != 'valid' for r in finished)
    run['status'] = 'complete_with_invalid_observations' if run['invalid_cells'] else 'complete'
    controls.write_json(output / 'run.json', run)
    report(output, run)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
