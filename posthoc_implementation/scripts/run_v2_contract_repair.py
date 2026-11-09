#!/usr/bin/env python3
"""One bounded model-authored graph/input patch using public contract feedback."""
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
import audit_v2_candidate_contracts as audit

generation = audit.generation
controls, replay, parent = audit.controls, audit.replay, audit.parent
CONFIG = ROOT / 'audit/v2/contract_repair.json'
PUBLIC_CONTRACT = ROOT / 'audit/v2/PUBLIC_ARTIFACT_INPUT_CONTRACT.md'
TESTS = ROOT / 'tests/unit/test_v2_contract_repair.py'
FILES = [Path(__file__).resolve(), CONFIG, PUBLIC_CONTRACT, TESTS, ROOT / 'audit/v2/CONTRACT_REPAIR.md']


def allowed_paths(document):
    return ['/artifacts', '/control_flow'] + [
        f'/{section}/{index}/{field}'
        for section, fields in [('service_intents', ('inputs', 'outputs')),
                                ('bindings', ('input_bindings', 'output_bindings'))]
        for index in range(len(document[section])) for field in fields]


def response_schema(document):
    paths = allowed_paths(document)
    return {'type': 'object', 'required': ['patch', 'unresolved_requirements'], 'additionalProperties': False,
            'properties': {
                'patch': {'type': 'array', 'minItems': 1, 'maxItems': len(paths), 'items': {
                    'type': 'object', 'required': ['op', 'path', 'value'], 'additionalProperties': False,
                    'properties': {'op': {'const': 'replace'}, 'path': {'enum': paths}, 'value': {}}}},
                'unresolved_requirements': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}}}


def apply_response(document, response):
    audit.repair.Validator(response_schema(document)).validate(response)
    patch = response['patch']
    if len({op['path'] for op in patch}) != len(patch):
        raise ValueError('Duplicate replacement path')
    candidate = copy.deepcopy(document)
    # The allowed paths do not overlap and never include roster entries as a
    # whole. Existing intent/service identity, ordering and parameters stay fixed.
    for op in patch:
        parts = op['path'].strip('/').split('/')
        target = candidate
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        key = int(parts[-1]) if isinstance(target, list) else parts[-1]
        if (isinstance(target, dict) and key not in target):
            raise ValueError('Replacement cannot create a missing field')
        target[key] = copy.deepcopy(op['value'])
    return candidate


def inspect_candidate(document, schema, workspace, context, manifest):
    catalog = generation.census.Catalog()
    analysis = audit.inspect(document, schema, workspace, context, catalog)
    review = audit.context_review(document, [p['path'] for p in manifest['files']])
    inputs = analysis['external_inputs']
    unresolved_links = [row for row in inputs if row['state'] not in (
        'literal_and_active_files_present', 'active_files_present_literal_differs')]
    return {'analysis': analysis, 'context': review, 'unresolved_bound_input_links': unresolved_links,
            'multi_writer_artifacts_need_registered_merge': bool(review['multiple_writer_artifacts']),
            'execution_ready': False, 'semantic_outcome': 'not_measured'}


def assess(payload, document, schema):
    row = generation.transport.observe(payload)
    text = row.pop('text', None)
    row.update(semantic_outcome='not_measured', public_gates='not_remeasured', patch_applied=False)
    if row['status'] != 'complete_text':
        return row, None, None
    try:
        response = generation.compact_ir.strict_json(text)
        candidate = apply_response(document, response)
    except Exception as exc:
        row.update(status='rejected_patch', error_type=type(exc).__name__, error_message=str(exc)[:2000])
        return row, None, None
    errors = audit.repair.errors(candidate, schema)
    row.update(patch_applied=True, patch_operations=len(response['patch']),
               changed_paths=[op['path'] for op in response['patch']],
               unresolved_requirements=response['unresolved_requirements'], schema_errors_after=errors,
               schema_conformant=not errors,
               status='schema_conformant_patch' if not errors else 'patch_schema_error',
               only_authorized_fields_changed=True)
    return row, response, candidate


def build_request(model, original_user, document, schema, feedback, public_contract):
    messages = [{'role': 'system', 'content':
        'Repair only the allowed artifact and port-binding fields using public contracts. '
        'Return exactly one JSON object with patch and unresolved_requirements, without fences, '
        'tools, or explanation. Choose all edits yourself. Do not invent missing source data, '
        'paths, transformations, or hidden answers. A schema or contract pass is not semantic success.'},
        copy.deepcopy(original_user),
        {'role': 'assistant', 'content': json.dumps(document, separators=(',', ':'))},
        {'role': 'user', 'content':
         'NEW PUBLIC V2 ARTIFACT/INPUT CONTRACT\n' + public_contract +
         '\nOFFLINE PUBLIC-CONTRACT FEEDBACK\n' + json.dumps(feedback, separators=(',', ':')) +
         '\nKeep service choices/versions, parameters, policies, runtime, public identity, and all other '
         'unlisted fields fixed. Replace whole allowed lists/objects where needed; no add/remove operations. '
         'Do not pretend a missing source has become available. Report unresolved requirements explicitly. '
         'The complete candidate still must satisfy the original full IR schema. Return only the response '
         'object under this patch schema:\n' + json.dumps(response_schema(document), separators=(',', ':'))}]
    return generation.transport.request(model, messages)


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 1:
        raise ValueError('One contract-repair request maximum')
    # This independently verifies/reproduces the earlier restricted enum patch.
    _, previous, _, document, _, schema, workspace, context, manifest, hashes = audit.prepare()
    root = ROOT / design['parent_audit']
    completed = replay.read_json(root / 'run.json')
    if (completed['status'] != 'complete' or completed.get('source_inputs_unchanged') is not True
            or completed['case'] != previous['case'] or completed['model_id'] != previous['model_id']):
        raise ValueError('Completed unchanged contract audit required')
    pinned = parent.verify_hashes(root, completed)
    generation.verify_completed(completed)
    if any(k in hashes and hashes[k] != v for k, v in pinned.items()):
        raise ValueError('Parent pins conflict')
    hashes.update(pinned)
    source_root = ROOT / previous['design']['parent_generation']
    source = replay.read_json(source_root / 'run.json')
    feedback = inspect_candidate(document, schema, workspace, context, manifest)
    if not audit.non_schema_hard(feedback['analysis']['findings']):
        raise ValueError('No checked contract/dataflow finding justifies this repair pilot')
    model = copy.deepcopy(source['model_config'])
    budget = design['requested_max_tokens']
    if not isinstance(budget, int) or isinstance(budget, bool) or not 1 <= budget <= model['max_tokens']:
        raise ValueError('Repair budget must not exceed the original output budget')
    model['max_tokens'] = budget
    public_contract = PUBLIC_CONTRACT.read_text()
    user = source['requests']['full_ir_json']['messages'][1]
    request = build_request(model, user, document, schema, feedback, public_contract)
    paths = [*FILES, root / 'run.json', root / 'input_sha256.json']
    for saved in completed['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    return design, previous, model, request, document, schema, workspace, context, manifest, feedback, hashes


def execute(attempt, request, model, secret, document, schema, workspace, context, manifest, client_factory=None):
    attempt.mkdir(parents=True, exist_ok=True)
    completion = attempt / 'completion.json'
    dispatch = attempt / 'dispatched.json'
    if not completion.is_file():
        if dispatch.is_file():
            return {'status': 'interrupted_outcome_unknown', 'semantic_outcome': 'not_measured'}
        controls.write_json(attempt / 'request.json', generation.transport.sanitize(request, secret))
        controls.write_json(dispatch, {'dispatched_at': datetime.now(timezone.utc).isoformat(), 'automatic_retries': 0})
        controls.write_json(completion, generation.transport.complete(model, request, secret, client_factory))
    payload = replay.read_json(completion)
    observed = generation.transport.observe(payload)
    if isinstance(observed.get('text'), str):
        (attempt / 'assistant_patch.txt').write_text(observed['text'])
    row, response, candidate = assess(payload, document, schema)
    row['latency_s'] = payload.get('latency_s')
    if response is not None:
        controls.write_json(attempt / 'model_patch.json', response)
        controls.write_json(attempt / 'candidate_ir.json', candidate)
        if row['schema_conformant']:
            findings = inspect_candidate(candidate, schema, workspace, context, manifest)
            controls.write_json(attempt / 'after_inspection.json', findings)
            row['non_schema_hard_findings_after'] = len(audit.non_schema_hard(findings['analysis']['findings']))
            row['unresolved_bound_input_links'] = len(findings['unresolved_bound_input_links'])
            row['explicit_fixture_links'] = len(findings['context']['artifact_fixture_links'])
            row['multiple_writer_artifacts'] = len(findings['context']['multiple_writer_artifacts'])
            row['inspection_errors'] = findings['analysis']['finding_counts'].get('inspection_error', 0)
    row['execution_ready'] = False
    controls.write_json(attempt / 'result.json', row)
    return row


def render(run):
    row = run['results'].get('contract_repair', {})
    return '\n'.join(['# V2 public-contract graph/input repair', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; model {run['model_id']}.",
        f"Case: {run['case']}; at most one new request. No workflow execution or semantic score.", '',
        f"- Repair outcome: {row.get('status', 'pending')}",
        f"- Model-authored patch operations: {row.get('patch_operations')}",
        f"- Schema conformant: {row.get('schema_conformant')}",
        f"- Checked non-schema contract/dataflow findings before: {run['hard_findings_before']}",
        f"- Checked non-schema contract/dataflow findings after: {row.get('non_schema_hard_findings_after')}",
        f"- Explicit artifact fixture links after: {row.get('explicit_fixture_links')}",
        f"- Unresolved bound-input links after: {row.get('unresolved_bound_input_links')}",
        f"- Multiple-writer artifacts after: {row.get('multiple_writer_artifacts')}",
        f"- Model-declared unresolved requirements: {json.dumps(row.get('unresolved_requirements'))}",
        f"- Completion tokens: {(row.get('usage') or {}).get('completion_tokens')}", '',
        'Service choices, parameters, policies, runtime, and public identity are protected; only listed patch paths are accepted.',
        'Zero checked defects does not prove meaningful input roles, operation semantics, or semantic correctness.',
        'The new public contract is a labeled v2 intervention. Original outputs, v1 scores, and submitted paper remain unchanged.', ''])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying contract audit and preparing one public-feedback graph/input patch...', flush=True)
    design, previous, model, request, document, schema, workspace, context, manifest, feedback, hashes = prepare()
    hard_before = len(audit.non_schema_hard(feedback['analysis']['findings']))
    if args.dry_run:
        print(json.dumps({'case': previous['case'], 'model': previous['model_id'], 'hard_findings_before': hard_before,
                          'allowed_patch_paths': len(allowed_paths(document)), 'maximum_new_requests': 1,
                          'requested_max_tokens': model['max_tokens'], 'automatic_retries': 0,
                          'workflow_executions': 0, 'semantic_scores': False}, indent=2))
        return 0
    secret = os.environ.get(model['api_key_env'])
    if not secret:
        raise ValueError('Set ' + model['api_key_env'] + ' in your terminal')
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if (run['input_fingerprint'] != controls.fingerprint(hashes) or run['request'] != request
                or run['model_config'] != model or run['design'] != design):
            raise ValueError('Repair code/design/inputs changed; cannot resume')
        generation.verify_completed(run)
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_contract_repair__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
               'design': design, 'case': previous['case'], 'model_id': previous['model_id'], 'model_config': model,
               'request': generation.transport.sanitize(request, secret), 'input_fingerprint': controls.fingerprint(hashes),
               'environment': controls.environment(), 'hard_findings_before': hard_before, 'results': {}, 'result_files': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        controls.write_json(output / 'before_inspection.json', feedback)
        for path in FILES:
            target = output / 'implementation' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    run['status'] = 'running'
    controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS), str(audit.TESTS)],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        print('verification_failed: ' + str(output / 'verification.txt'), flush=True)
        return 1
    if 'contract_repair' not in run['results']:
        parent.verify_hashes(output, run)
        attempt = output / 'cells/contract_repair'
        row = execute(attempt, request, model, secret, document, schema, workspace, context, manifest)
        controls.write_json(attempt / 'result.json', row)
        run['results']['contract_repair'] = row
        run['result_files']['contract_repair'] = generation.output_checkpoint(attempt)
        controls.write_json(output / 'run.json', run)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    row = run['results']['contract_repair']
    failure = row['status'] in ('inference_error', 'interrupted_outcome_unknown') or row.get('inspection_errors', 0)
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if failure else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
