#!/usr/bin/env python3
"""Reference integration gate for the real, fail-closed semantic backend."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_backend_controls as prior
import semantic_backend as backend

generation, controls, replay, parent = prior.generation, prior.controls, prior.replay, prior.parent
CONFIG = ROOT / 'audit/v2/semantic_integration.json'
TESTS = ROOT / 'tests/unit/test_v2_semantic_integration.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/semantic_backend.py',
         ROOT / 'audit/v2/SEMANTIC_INTEGRATION.md']


def public_control_view(ir, workspace):
    """Reference-control provenance only; never repair a model prediction."""
    manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, manifest)
    if any(ir['source'][key] != manifest['instance'][other] for key, other in (
            ('benchmark_id', 'benchmark_id'), ('split', 'split'), ('pipeline_id', 'id'))):
        raise ValueError('Reference control and public task identities disagree')
    metadata = generation.public_metadata(workspace, manifest, {
        'source_dataset_id': ir['source']['dataset_id'],
        'source_dataset_version': ir['source']['dataset_version']})
    projected = copy.deepcopy(ir)
    edits = []
    for key, value in metadata.items():
        if projected[key] != value:
            edits.append({'path': '/' + key, 'old_value': projected[key], 'value': value,
                          'rule': 'verified_public_reference_control_bookkeeping'})
            projected[key] = value
    lines = (workspace / 'task.md').read_text().splitlines()
    for index, intent in enumerate(projected['service_intents']):
        evidence = []
        if not intent['source_step_refs']:
            raise ValueError('Reference control requires explicit public source-step references')
        for reference in intent['source_step_refs']:
            matches = [n for n, line in enumerate(lines)
                       if re.match(r'^\d+\.\s+' + re.escape(reference) + r'\s+-\s+', line)]
            if len(matches) != 1:
                raise ValueError('Cannot cite an unambiguous public task step for the reference control')
            start = matches[0]
            end = start + 1 if start + 1 < len(lines) and lines[start + 1].strip().startswith('- Objective:') else start
            evidence.append({'source': 'description', 'text': '\n'.join(lines[start:end + 1]),
                             'line_start': start + 1, 'line_end': end + 1})
        if intent['evidence'] != evidence:
            edits.append({'path': f'/service_intents/{index}/evidence', 'old_value': intent['evidence'],
                          'value': evidence, 'rule': 'reference_control_verified_public_step_evidence'})
            intent['evidence'] = evidence
    if any(ir[k] != projected[k] for k in ir if k not in (*generation.compact_ir.BOOKKEEPING, 'service_intents')):
        raise ValueError('Control metadata projection changed a business decision')
    for before, after in zip(ir['service_intents'], projected['service_intents']):
        if {k: v for k, v in before.items() if k != 'evidence'} != {k: v for k, v in after.items() if k != 'evidence'}:
            raise ValueError('Public citation projection changed an intent decision')
    return projected, edits


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference permitted')
    root = ROOT / design['parent_backend_controls']
    completed = replay.read_json(root / 'run.json')
    if completed['status'] != 'complete' or completed.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged backend comparison required')
    hashes = parent.verify_hashes(root, completed)
    generation.verify_completed(completed)
    actual = {p.relative_to(root).as_posix(): controls.sha256(p) for p in (root / 'mock_execution').rglob('*') if p.is_file()}
    if actual != completed['execution_file_sha256']:
        raise ValueError('Mock control execution evidence changed')
    if (not all(r['pass'] for r in completed['results']['cached_real_profile_execution'].values())
            or not all(r['detected'] for r in completed['negative_controls'].values())):
        raise ValueError('Real-profile/checker controls must pass before integration')
    _, ir, old_profile, workspace, fixtures, _, prior_hashes = prior.prepare()
    if any(k in hashes and hashes[k] != v for k, v in prior_hashes.items()):
        raise ValueError('Parent fingerprints conflict')
    hashes.update(prior_hashes)
    profile_path = ROOT / design['profile']
    profile = replay.read_json(profile_path)
    if any(profile[key] != old_profile[key] for key in ('profile_version', 'fields', 'input_keys', 'rules')):
        raise ValueError('Business semantics changed from the verified public controls')
    ir, bookkeeping_edits = public_control_view(ir, workspace)
    plan = backend.compile_plan(ir, profile)
    plan['reference_control_provenance_edits'] = bookkeeping_edits
    schema = controls.load(workspace / 'schemas/serviceflow_ir.schema.json')
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema).validate(ir)
    artifact_schemas = prior.real.base.schemas_for(ir, workspace)
    scenarios = design['positive_scenarios'] + design['rejection_scenarios']
    if len(set(scenarios)) != len(scenarios) or set(scenarios) != set(old_profile['scenarios']):
        raise ValueError('Retain the complete nine-scenario control roster')
    paths = [*FILES, profile_path, root / 'run.json', root / 'input_sha256.json']
    for saved in completed['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    paths.extend(root / name for name in completed['execution_file_sha256'])
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    return design, ir, profile, fixtures, schema, artifact_schemas, plan, hashes


def evaluate(result, ir, fixtures, profile, design, artifact_schemas=None):
    name = result['scenario']
    if name in design['positive_scenarios']:
        checked = prior.neutral_check(result, ir, fixtures, profile)
        kind = 'positive_business_output'
    else:
        # Reuse the established negative-input oracle for specific rejection
        # reasons and non-publication, not arbitrary process failure.
        checked = prior.real.oracle.check(result, ir, fixtures, profile, name)
        kind = 'expected_input_rejection'
    try:
        receipt = json.loads(result['_snapshot']['logs/semantic_backend_receipt.json'])
        valid_receipt = (receipt['backend_id'] == backend.BACKEND_ID
            and receipt['profile_sha256'] == backend.digest(profile)
            and receipt['ir_sha256'] == backend.digest(ir)
            and receipt['strict_labels_verified'] is True and receipt['mock_fallback'] is False
            and receipt['label_replacements'] == [])
    except (KeyError, ValueError, TypeError):
        valid_receipt = False
    checked['checks'].append({'check': 'real_backend_exact_profile_receipt', 'pass': valid_receipt})
    from jsonschema import Draft202012Validator
    for identity, schema in (artifact_schemas or {}).items():
        path = 'artifacts/' + identity + '.json'
        if path not in result['_snapshot']:
            continue
        try:
            Draft202012Validator(schema).validate(json.loads(result['_snapshot'][path]))
            passed = True
        except Exception:
            passed = False
        checked['checks'].append({'check': 'produced_public_artifact_schema:' + identity, 'pass': passed})
    checked['pass'] = checked['pass'] and all(c['pass'] for c in checked['checks'])
    return {**checked, 'kind': kind}


def render(run):
    lines = ['# V2 semantic runtime-package integration controls', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; backend {backend.BACKEND_ID}.",
        'Reference controls only; no LLM calls, original model reruns, or original-score changes.', '',
        '| Scenario | Control kind | Passed |', '|---|---|---|']
    for name, row in run.get('results', {}).items():
        lines.append(f"| {name} | {row['kind']} | {row['pass']} |")
    lines += ['', f"Business-negative controls detected: {sum(v['detected'] for v in run.get('negative_controls', {}).values())}/{len(run['design']['negative_controls'])}.", '',
        'Six positive business-output cases and three correct input rejections are distinct outcomes, not nine successful workflow executions.',
        'The registered backend validates exact operation labels and explicit fixture links; unsupported operations never fall back to mock outputs.',
        'This validates one supported family and runtime-package export, not complete M0–M5 integration, Argo deployment, corpus coverage, or model semantic accuracy.',
        'Original v1, paper, deposit, scores and audit evidence remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying real-backend registry, strict input contracts and completed controls...', flush=True)
    design, ir, profile, fixtures, schema, artifact_schemas, plan, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'backend': backend.BACKEND_ID, 'profile': profile['profile_version'],
                          'registered_services': len(backend.window.OPERATIONS), 'exact_labels_required': True,
                          'mock_fallback': False, 'new_positive_scenarios': len(design['positive_scenarios']),
                          'expected_rejection_scenarios': len(design['rejection_scenarios']),
                          'api_requests': 0, 'model_workflows_executed': 0, 'verified_inputs': len(hashes)}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/outputs' / f'package_v2_semantic_integration__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
           'status': 'running', 'results': {}, 'result_files': {}}
    controls.write_json(output / 'input_sha256.json', hashes)
    controls.write_json(output / 'run.json', run)
    for path in [*FILES, ROOT / design['profile']]:
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
    names = design['positive_scenarios'] + design['rejection_scenarios']
    scenarios = [{'name': n, 'parameters': {}, 'fixture_root': 'fixtures/scenarios/' + n} for n in names]
    instance = output / 'instance'
    manifest = backend.materialize_runtime(ir, profile, scenarios, instance, schema)
    shutil.copytree(fixtures, instance / 'fixtures')
    raw = controls._execute_scenarios(instance, manifest, sandbox_generated=True)
    controls.persist_snapshots(raw, output / 'execution')
    if {r['scenario'] for r in raw} != set(names):
        raise ValueError('Do not publish partial integration controls')
    for result in raw:
        name = result['scenario']
        run['results'][name] = evaluate(result, ir, fixtures / 'scenarios' / name, profile, design, artifact_schemas)
    nominal = next(r for r in raw if r['scenario'] == 'nominal')
    negatives = {}
    if run['results']['nominal']['pass']:
        for condition in design['negative_controls']:
            mutant = prior.mutate(nominal, ir, condition)
            result = prior.neutral_check(mutant, ir, fixtures / 'scenarios/nominal', profile)
            negatives[condition] = {'detected': not result['pass'], 'evaluation': result}
    run['negative_controls'] = negatives
    evidence = output / 'evidence'
    controls.write_json(evidence / 'result.json', {'results': run['results'], 'negative_controls': negatives, 'compile_plan': plan})
    run['result_files']['semantic_integration'] = generation.output_checkpoint(evidence)
    run['execution_file_sha256'] = {p.relative_to(output).as_posix(): controls.sha256(p)
                                   for p in (output / 'execution').rglob('*') if p.is_file()}
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    passed = all(r['pass'] for r in run['results'].values()) and len(negatives) == len(design['negative_controls']) and all(v['detected'] for v in negatives.values())
    run['status'] = 'inputs_changed' if not unchanged else 'complete' if passed else 'control_failed'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
