#!/usr/bin/env python3
"""One user-run generation call with raw/assembly conditions and real execution."""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import json
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_semantic_integration as integration
import binding_assembly

generation = integration.generation
controls, replay, parent = integration.controls, integration.replay, integration.parent
CONFIG = ROOT / 'audit/v2/semantic_generation.json'
RULES = ROOT / 'audit/v2/runtime_profiles/IR_INPUT_OUTPUT_RULES.md'
TESTS = ROOT / 'tests/unit/test_v2_semantic_generation.py'
FILES = [Path(__file__).resolve(), CONFIG, RULES, TESTS, ROOT / 'audit/v2/SEMANTIC_GENERATION.md',
         ROOT / 'audit/v2/binding_assembly.py', generation.MODELS]


def file_hashes(directory):
    return {p.relative_to(directory).as_posix(): controls.sha256(p) for p in directory.rglob('*') if p.is_file()}


def parsed_data(path):
    text = path.read_text()
    if path.suffix == '.json':
        value = generation.compact_ir.strict_json(text)
    elif path.suffix in ('.jsonl', '.ndjson'):
        value = [generation.compact_ir.strict_json(line) for line in text.splitlines() if line.strip()]
    elif path.suffix == '.csv':
        value = list(csv.reader(io.StringIO(text), strict=True))
    else:
        return path.read_bytes()
    # Preserve scalar types, numeric representations, row order and duplicates.
    # Normalize object-key order and representation whitespace only.
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def nominal_alignment(public, controlled):
    first, second = file_hashes(public), file_hashes(controlled)
    if not first or set(first) != set(second):
        raise ValueError('Nominal public/control file roster differs')
    changes = []
    for name in first:
        if first[name] == second[name]:
            continue
        if parsed_data(public / name) != parsed_data(controlled / name):
            raise ValueError('Nominal input values differ; do not proceed with inference')
        changes.append({'file': name, 'public_sha256': first[name], 'prior_control_sha256': second[name],
                        'relation': 'parse_identical_serialization_difference'})
    return {'policy': 'execute_byte_exact_public_nominal_inputs', 'public_files': first,
            'prior_control_files': second, 'serialization_differences': changes,
            'note': 'Other declared evaluation variants remain unchanged; no values or sources are invented.'}


def stage_fixtures(source, public_nominal, destination):
    alignment = nominal_alignment(public_nominal, source / 'scenarios/nominal')
    if destination.exists():
        raise ValueError('An interrupted fixture-bank staging must not be silently overwritten')
    shutil.copytree(source, destination)
    shutil.rmtree(destination / 'scenarios/nominal')
    shutil.copytree(public_nominal, destination / 'scenarios/nominal')
    if file_hashes(public_nominal) != file_hashes(destination / 'scenarios/nominal'):
        raise ValueError('Staged evaluation nominal input bytes do not match public input bytes')
    return alignment


def build_request(model, workspace, manifest, design, schema, metadata, profile, intake, policy):
    messages = generation.messages(workspace, manifest, design, 'full_ir_json', schema, metadata)
    operations = [{'service_id': key, 'service_version': '1.0.0', 'operation_profile': value[0]}
                  for key, value in sorted(integration.backend.window.OPERATIONS.items())]
    messages[1]['content'] += (
        '\nPUBLIC SEMANTIC EXECUTION CONTRACT\n' + RULES.read_text() +
        '\nPUBLIC NUMERICAL PROFILE\n' + json.dumps(profile, separators=(',', ':')) +
        '\nREGISTERED SERVICE OPERATIONS\n' + json.dumps(operations, separators=(',', ':')) +
        '\nPUBLIC INPUT RESOURCE ROLE\n' + json.dumps(intake, separators=(',', ':')) +
        '\nDECLARED ASSEMBLY POLICY (SEPARATE FROM RAW OUTPUT)\n' + json.dumps(policy, separators=(',', ':')) +
        '\nReturn only the complete minified ServiceFlowIR JSON object. Do not return code, a patch, or a test result.')
    return generation.transport.request(model, messages)


def prepare(model_id=None):
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 1 or design['repair_requests'] != 0 or design['conditions'] != ['raw', 'assembled']:
        raise ValueError('Fixed single-call, zero-repair paired design required')
    root = ROOT / design['parent_integration']
    verified = replay.read_json(root / 'run.json')
    if verified['status'] != 'complete' or verified.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged real-backend integration required')
    hashes = parent.verify_hashes(root, verified)
    generation.verify_completed(verified)
    actual = {p.relative_to(root).as_posix(): controls.sha256(p) for p in (root / 'execution').rglob('*') if p.is_file()}
    if actual != verified['execution_file_sha256']:
        raise ValueError('Integration snapshots changed')
    if (not all(v['pass'] for v in verified['results'].values()) or
            not all(v['detected'] for v in verified['negative_controls'].values())):
        raise ValueError('Integration business/rejection/mutation controls must all pass')
    for field in ('positive_scenarios', 'rejection_scenarios'):
        if design[field] != verified['design'][field]:
            raise ValueError('Scenario roster differs from verified integration')
    model_id = model_id or design['default_model']
    models = replay.read_json(generation.MODELS)['models']
    if model_id not in models:
        raise ValueError('Choose one configured model')
    model = copy.deepcopy(models[model_id])
    generation.transport.validate_model(model)
    inventory_file = ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json'
    inventory = replay.read_json(inventory_file)
    workspace = Path(inventory['control_directory']) / 'cases' / design['case'] / 'public_workspace' / design['case']
    context = generation.census.public_context(workspace)
    manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, manifest)
    if manifest['instance']['split'] + '/' + manifest['instance']['id'] != design['case']:
        raise ValueError('Wrong public task workspace')
    schema = controls.load(workspace / 'schemas/serviceflow_ir.schema.json')
    metadata = generation.public_metadata(workspace, manifest, design)
    codec = generation.compact_ir.Codec(schema, metadata)
    profile = replay.read_json(ROOT / design['profile'])
    integration.backend.verify_profile(profile)
    policy = replay.read_json(ROOT / design['assembly_policy'])
    if policy['policy_version'] != 'v2-explicit-binding-assembly/1':
        raise ValueError('Unsupported assembly policy')
    active = workspace / 'fixtures/scenarios/nominal'
    matches = integration.prior.real.repairer.manifests(active, profile)
    if len(matches) != 1:
        raise ValueError('A unique complete public input manifest is required before inference')
    intake = {'role': 'external_json_manifest', 'fixture_ref': 'fixtures/inputs/' + matches[0],
              'public_nominal_path': 'fixtures/scenarios/nominal/' + matches[0],
              'discovery': 'unique public JSON manifest with required input roles and batch configuration'}
    fixtures = root / 'instance/fixtures'
    nominal = fixtures / 'scenarios/nominal'
    nominal_alignment(active, nominal)
    request = build_request(model, workspace, manifest, design, schema, metadata, profile, intake, policy)
    paths = [*FILES, ROOT / design['profile'], ROOT / design['assembly_policy'], inventory_file,
             root / 'run.json', root / 'input_sha256.json', workspace / 'workspace.yaml']
    for saved in verified['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    paths.extend(root / name for name in verified['execution_file_sha256'])
    paths.extend(p for p in fixtures.rglob('*') if p.is_file())
    paths.extend(workspace / row['path'] for row in manifest['files'])
    for path in paths:
        name, digest = str(path.resolve()), controls.sha256(path)
        if name in hashes and hashes[name] != digest:
            raise ValueError('Pinned input changed')
        hashes[name] = digest
    return design, model_id, model, workspace, context, schema, metadata, codec, profile, intake, policy, fixtures, request, hashes


def inspect_candidate(candidate, schema, workspace, context, profile):
    from jsonschema import Draft202012Validator
    errors = list(Draft202012Validator(schema).iter_errors(candidate))
    if errors:
        return {'state': 'blocked_schema', 'errors': [e.message for e in errors[:20]]}
    if candidate.get('runtime', {}).get('execution_profile') != 'reference':
        return {'state': 'unsupported_runtime_selection',
                'reason': 'This declared local semantic condition requires runtime.execution_profile=reference'}
    catalog = generation.census.Catalog()
    analysis = generation.census.analysis.analyze(candidate, schema=schema,
        catalog_get=lambda s, v: catalog.get(workspace, s, v), workspace=workspace,
        scenarios=context['scenarios'], load=controls.load)
    record = {'public_static_diagnostics': analysis}
    if analysis['finding_counts'].get('inspection_error'):
        return {**record, 'state': 'inspection_error'}
    hard = [f for f in analysis['findings'] if f['category'] in generation.census.analysis.HARD]
    if hard:
        return {**record, 'state': 'blocked_public_contracts', 'hard_finding_count': len(hard)}
    try:
        plan = integration.backend.compile_plan(candidate, profile)
        schemas = integration.prior.real.base.schemas_for(candidate, workspace)
    except integration.backend.ops.Unsupported as exc:
        return {**record, 'state': 'unsupported_runtime_scope', 'reason': str(exc)}
    except (ValueError, KeyError, TypeError) as exc:
        return {**record, 'state': 'invalid_runtime_contract', 'reason': type(exc).__name__ + ': ' + str(exc)}
    return {**record, 'state': 'ready', 'compile_plan': plan, 'artifact_schemas': schemas}


def run_condition(attempt, candidate, schema, workspace, context, profile, fixtures, design, assembly):
    attempt.mkdir(parents=True, exist_ok=True)
    if (attempt / 'result.json').is_file():
        return replay.read_json(attempt / 'result.json')
    row = {'assembly': assembly, 'evaluated': False, 'profile_all_controls_pass': None,
           'original_g6_assert': 'not_measured', 'original_full_public_gates': 'not_measured'}
    if (attempt / 'execution_started.json').is_file():
        row.update(state='interrupted_execution_unknown')
        controls.write_json(attempt / 'result.json', row)
        return row
    controls.write_json(attempt / 'candidate_ir.json', candidate)
    inspected = inspect_candidate(candidate, schema, workspace, context, profile)
    row.update(inspected)
    if inspected['state'] != 'ready':
        controls.write_json(attempt / 'result.json', row)
        return row
    controls.write_json(attempt / 'execution_started.json', {'at': datetime.now(timezone.utc).isoformat(),
        'note': 'Fixed isolated attempt; do not automatically re-execute after ambiguous interruption'})
    scenarios = [{'name': name, 'parameters': {}, 'fixture_root': 'fixtures/scenarios/' + name}
                 for name in design['positive_scenarios'] + design['rejection_scenarios']]
    try:
        instance = attempt / 'instance'
        manifest = integration.backend.materialize_runtime(candidate, profile, scenarios, instance, schema)
        shutil.copytree(fixtures, instance / 'fixtures')
        results = controls._execute_scenarios(instance, manifest, sandbox_generated=True)
        controls.persist_snapshots(results, attempt / 'execution')
        if {r['scenario'] for r in results} != {s['name'] for s in scenarios}:
            raise ValueError('Incomplete runtime scenario roster')
        evaluations = {r['scenario']: integration.evaluate(r, candidate, fixtures / 'scenarios' / r['scenario'],
            profile, design, inspected['artifact_schemas']) for r in results}
        row.update(state='evaluated', evaluated=True, scenarios=evaluations,
                   profile_all_controls_pass=all(r['pass'] for r in evaluations.values()),
                   positive_passes=sum(v['pass'] for v in evaluations.values() if v['kind'] == 'positive_business_output'),
                   correct_rejections=sum(v['pass'] for v in evaluations.values() if v['kind'] == 'expected_input_rejection'))
    except Exception as exc:
        row.update(state='runtime_or_inspection_error', error_type=type(exc).__name__, reason=str(exc))
    controls.write_json(attempt / 'result.json', row)
    return row


def render(run):
    gen = run.get('generation', {})
    usage = gen.get('usage') or {}
    lines = ['# V2 real-backend single-generation pilot', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; model {run['model_id']}.",
        f"Case {run['design']['case']}; one sampled answer, at most one inference request, zero repair calls.",
        'Exploratory explicit-profile IR generation; not M3-vs-M4 or a new original G6/model-accuracy estimate.', '',
        f"Generation outcome: {gen.get('status')}; finish: {gen.get('finish_reason')}; completion tokens: {usage.get('completion_tokens')}.", '',
        '| Condition | State | Assembly operations | Positive checks | Correct rejections | Reused execution |',
        '|---|---|---:|---|---|---|']
    for name in run['design']['conditions']:
        row = run['conditions'].get(name, {})
        positives = str(row['positive_passes']) + '/6' if row.get('evaluated') else 'not executed'
        rejected = str(row['correct_rejections']) + '/3' if row.get('evaluated') else 'not executed'
        lines.append(f"| {name} | {row.get('state', 'pending')} | {len(row.get('assembly', {}).get('operations', []))} | {positives} | {rejected} | {row.get('execution_reused_from', '-')} |")
    lines += ['', 'Raw and assembled are paired conditions of one answer, not independent samples. Identical IR reuses the same execution with an explicit receipt.',
        'Assembly supplies only declared redundant-list/status-declaration policy; no service, parameter, source choice, business wiring, or business value is repaired.',
        'Blocked/unsupported outcomes remain recorded; they are not inferred semantic successes or silently dropped observations.',
        'Literal v1 type-comparison findings remain separate from this declared JSON-bundle profile; no full G0–G5/Argo pass is claimed.',
        'The model sees nominal public inputs and operation rules only. Evaluation variants, reference IR, cached results, and private assertions are not prompt inputs.',
        'All cases have been inspected during development; report input perturbations as development robustness checks, not untouched task generalization.',
        'Original v1, scores, submitted paper, deposit and earlier audit records remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying real-backend controls and preparing one public-only generation request...', flush=True)
    (design, model_id, model, workspace, context, schema, metadata, codec, profile, intake,
     policy, fixtures, request, hashes) = prepare(args.model)
    if args.dry_run:
        print(json.dumps({'case': design['case'], 'model': model_id, 'maximum_inference_requests': 1,
            'repair_calls': 0, 'requested_max_tokens': model['max_tokens'], 'conditions': design['conditions'],
            'maximum_runtime_scenarios': 18, 'public_input_role': intake, 'verified_inputs': len(hashes),
            'prompt_characters': sum(len(m['content']) for m in request['messages']),
            'private_answers_or_reference_ir_in_prompt': False, 'original_scores_replaced': False}, indent=2))
        return 0
    secret = os.environ.get(model['api_key_env'])
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if (run['input_fingerprint'] != controls.fingerprint(hashes) or run['request'] != request
                or run['model_id'] != model_id or run['design'] != design):
            raise ValueError('Pilot code/design/configuration changed; cannot resume')
        generation.verify_completed(run)
    else:
        if not secret:
            raise ValueError('Set ' + model['api_key_env'] + ' in your terminal')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_semantic_generation__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
               'design': design, 'model_id': model_id, 'model_config': model, 'profile': profile, 'metadata': metadata,
               'request': generation.transport.sanitize(request, secret), 'public_input_role': intake,
               'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
               'conditions': {}, 'result_files': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        for path in [*FILES, ROOT / design['profile'], ROOT / design['assembly_policy']]:
            target = output / 'implementation' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    run['status'] = 'running'
    controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        print('verification_failed: ' + str(output / 'verification.txt'), flush=True)
        return 1
    if 'generation' not in run:
        parent.verify_hashes(output, run)
        attempt = output / 'generation'
        if not (attempt / 'completion.json').exists() and not (attempt / 'dispatched.json').exists() and not secret:
            raise ValueError('Set ' + model['api_key_env'] + ' before the pending inference request')
        row = generation.run_cell(attempt, 'full_ir_json', request, model, secret, codec, schema, workspace, context)
        controls.write_json(attempt / 'result.json', row)
        run['generation'] = row
        run['result_files']['generation'] = generation.output_checkpoint(attempt)
        controls.write_json(output / 'run.json', run)
    eligible = (run['generation'].get('schema_conformant') is True and run['generation'].get('metadata_conformant') is True
                and run['generation']['status'] in ('complete_ir', 'complete_ir_with_length_stop'))
    raw = replay.read_json(output / 'generation/expanded_ir.json') if eligible else None
    if eligible:
        evaluation_fixtures = output / 'evaluation_fixtures'
        if 'evaluation_fixture_files' in run:
            if file_hashes(evaluation_fixtures) != run['evaluation_fixture_files']:
                raise ValueError('Staged evaluation fixtures changed')
        else:
            alignment = stage_fixtures(fixtures, workspace / 'fixtures/scenarios/nominal', evaluation_fixtures)
            run['evaluation_nominal_alignment'] = alignment
            controls.write_json(evaluation_fixtures / 'result.json', {
                'role': 'audit_receipt_outside_all_scenario_input_roots', 'nominal_alignment': alignment,
                'data_file_sha256': file_hashes(evaluation_fixtures)})
            run['evaluation_fixture_files'] = file_hashes(evaluation_fixtures)
            run['result_files']['evaluation_inputs'] = generation.output_checkpoint(evaluation_fixtures)
            controls.write_json(output / 'run.json', run)
    else:
        evaluation_fixtures = fixtures
    for condition in design['conditions']:
        if condition in run['conditions']:
            continue
        parent.verify_hashes(output, run)
        attempt = output / 'conditions' / condition
        attempt.mkdir(parents=True, exist_ok=True)
        if not eligible:
            row = {'state': 'generation_not_eligible', 'evaluated': False, 'profile_all_controls_pass': None}
        elif condition == 'raw':
            row = run_condition(attempt, raw, schema, workspace, context, profile, evaluation_fixtures, design,
                                {'state': 'not_applied', 'operations': []})
        else:
            catalog = generation.census.Catalog()
            value, assembly = binding_assembly.assemble(raw, lambda s, v: catalog.get(workspace, s, v), policy)
            if assembly['state'] == 'blocked_no_changes':
                row = {'state': 'assembly_blocked', 'assembly': assembly, 'evaluated': False, 'profile_all_controls_pass': None}
            elif value == raw:
                row = {**copy.deepcopy(run['conditions']['raw']), 'assembly': assembly, 'execution_reused_from': 'raw',
                       'reuse_basis': 'Exact JSON equality of raw and assembled IR; one model answer, no second execution'}
            else:
                row = run_condition(attempt, value, schema, workspace, context, profile, evaluation_fixtures, design, assembly)
        controls.write_json(attempt / 'result.json', row)
        run['conditions'][condition] = row
        run['result_files'][condition] = generation.output_checkpoint(attempt)
        controls.write_json(output / 'run.json', run)
        (output / 'summary.md').write_text(render(run))
        print(condition + ': ' + row['state'], flush=True)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    errors = run['generation']['status'] in ('inference_error', 'interrupted_outcome_unknown') or any(
        v['state'] in ('runtime_or_inspection_error', 'interrupted_execution_unknown', 'inspection_error') for v in run['conditions'].values())
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if errors else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
