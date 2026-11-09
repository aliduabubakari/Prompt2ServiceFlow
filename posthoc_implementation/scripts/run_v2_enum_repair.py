#!/usr/bin/env python3
"""One user-run schema-feedback repair with tightly restricted JSON patches."""
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
Validator = generation.compact_ir.Draft202012Validator
CONFIG = ROOT / 'audit/v2/enum_repair.json'
TESTS = ROOT / 'tests/unit/test_v2_enum_repair.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/ENUM_REPAIR.md']


def pointer(parts):
    return ''.join('/' + str(p).replace('~', '~0').replace('/', '~1') for p in parts)


def enum_sites(document, schema):
    """Describe existing scalar enum failures; never invent their replacements."""
    sites = {}
    for error in Validator(schema).iter_errors(document):
        parts = list(error.absolute_path)
        if (error.validator != 'enum' or not parts
                or isinstance(error.instance, (dict, list))
                or any(isinstance(v, (dict, list)) for v in error.validator_value)):
            raise ValueError('This bounded protocol accepts only existing scalar enum failures')
        path = pointer(parts)
        if path in sites:
            raise ValueError('Ambiguous schema constraints at one repair path')
        sites[path] = {'path': path, 'parts': parts, 'current_value': copy.deepcopy(error.instance),
                       'allowed_values': copy.deepcopy(error.validator_value),
                       'schema_path': list(error.absolute_schema_path)}
    if not sites:
        raise ValueError('No enum repair is needed')
    return sites


def patch_schema(sites):
    choices = [{'type': 'object', 'additionalProperties': False,
                'required': ['op', 'path', 'value'],
                'properties': {'op': {'const': 'replace'}, 'path': {'const': path},
                               'value': {'enum': site['allowed_values']}}}
               for path, site in sites.items()]
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'type': 'array',
            'minItems': 1, 'maxItems': len(sites), 'items': {'oneOf': choices}}


def apply_patch(document, patch, sites):
    Validator(patch_schema(sites)).validate(patch)
    paths = [op['path'] for op in patch]
    if len(set(paths)) != len(paths):
        raise ValueError('Repeated repair path')
    result = copy.deepcopy(document)
    for op in patch:
        site = sites[op['path']]
        target = result
        for key in site['parts'][:-1]:
            target = target[key]
        key = site['parts'][-1]
        if target[key] != site['current_value']:
            raise ValueError('Original field changed before patch application')
        target[key] = copy.deepcopy(op['value'])
    return result


def errors(document, schema):
    return [{'path': pointer(list(e.absolute_path)), 'validator': e.validator,
             'message': e.message, 'schema_path': list(e.absolute_schema_path)}
            for e in Validator(schema).iter_errors(document)]


def build_request(model, original_messages, candidate_text, sites):
    if len(original_messages) != 2 or original_messages[1]['role'] != 'user':
        raise ValueError('Expected the original one-pass public context')
    # Preserve the complete public context; change the output instruction to a
    # patch rather than asking the model to regenerate all composition decisions.
    messages = [{'role': 'system', 'content':
        'Revise an existing ServiceFlowIR using only public task/catalog/schema information. '
        'The last user message specifies the response format: return exactly one JSON array '
        'of replace operations, with no fences, explanation, or tools. Never invent source '
        'data or hidden expected answers. Choose replacements consistent with the task; '
        'do not treat schema validity as semantic success.'},
        copy.deepcopy(original_messages[1]),
        {'role': 'assistant', 'content': candidate_text},
        {'role': 'user', 'content':
         'PUBLIC SCHEMA ENUM ERRORS\n' + json.dumps(list(sites.values()), separators=(',', ':')) +
         '\nReplace only the listed existing fields. The allowed values come from the public '
         'schema; the harness supplies no choice. Do not change services, bindings, fixtures, '
         'parameters, or other fields. A catalog capability property and an intent requirement '
         'can have different vocabularies; use the schema for the field being edited. '
         'Return the patch array under this schema:\n' + json.dumps(patch_schema(sites), separators=(',', ':'))}]
    return generation.transport.request(model, messages)


def assess(payload, document, schema, sites, metadata):
    observed = generation.transport.observe(payload)
    text = observed.pop('text', None)
    row = {**observed, 'semantic_outcome': 'not_measured', 'public_gates': 'not_remeasured',
           'schema_errors_before': errors(document, schema), 'patch_applied': False,
           'schema_conformant': None, 'metadata_conformant': None}
    if row['status'] != 'complete_text':
        return row, None, None
    try:
        patch = generation.compact_ir.strict_json(text)
        candidate = apply_patch(document, patch, sites)
    except Exception as exc:
        row.update(status='rejected_patch', error_type=type(exc).__name__, error_message=str(exc)[:2000])
        return row, None, None
    remaining = errors(candidate, schema)
    row.update(patch_applied=True, patch_operations=len(patch), changed_paths=[op['path'] for op in patch],
               schema_errors_after=remaining, schema_conformant=not remaining,
               metadata_conformant=all(candidate[k] == metadata[k] for k in generation.compact_ir.BOOKKEEPING),
               status='schema_repaired' if not remaining else 'remaining_schema_errors',
               only_authorized_fields_changed=True)
    return row, patch, candidate


def execute(attempt, request, model, secret, document, schema, sites, metadata, client_factory=None):
    attempt.mkdir(parents=True, exist_ok=True)
    completion = attempt / 'completion.json'
    dispatch = attempt / 'dispatched.json'
    if not completion.is_file():
        if dispatch.is_file():
            return {'status': 'interrupted_outcome_unknown', 'semantic_outcome': 'not_measured'}
        controls.write_json(attempt / 'request.json', generation.transport.sanitize(request, secret))
        controls.write_json(dispatch, {'dispatched_at': datetime.now(timezone.utc).isoformat(), 'automatic_retries': 0})
        payload = generation.transport.complete(model, request, secret, client_factory)
        controls.write_json(completion, payload)
    else:
        payload = replay.read_json(completion)
    observed = generation.transport.observe(payload)
    if isinstance(observed.get('text'), str):
        (attempt / 'assistant_patch.txt').write_text(observed['text'])
    row, patch, candidate = assess(payload, document, schema, sites, metadata)
    row['latency_s'] = payload.get('latency_s')
    if candidate is not None:
        controls.write_json(attempt / 'patch.json', patch)
        controls.write_json(attempt / 'candidate_ir.json', candidate)
    controls.write_json(attempt / 'result.json', row)
    return row


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 1:
        raise ValueError('One repair call maximum')
    folder = ROOT / design['parent_generation']
    previous = replay.read_json(folder / 'run.json')
    if previous['status'] != 'complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged generation evidence required')
    hashes = parent.verify_hashes(folder, previous)
    generation.verify_completed(previous)
    key = design['condition']
    attempt = Path(previous['results'][key]['artifact_directory'])
    payload = replay.read_json(attempt / 'completion.json')
    observed = generation.transport.observe(payload)
    if observed['status'] != 'complete_text':
        raise ValueError('A normally completed final-content response is required')
    text = observed['text']
    document = generation.compact_ir.strict_json(text)
    schema = replay.read_json(folder / 'full_output.schema.json')
    metadata = previous['metadata']
    if not all(document[k] == metadata[k] for k in generation.compact_ir.BOOKKEEPING):
        raise ValueError('Public identity mismatch is outside this repair protocol')
    sites = enum_sites(document, schema)
    model = copy.deepcopy(previous['model_config'])
    budget = design['requested_max_tokens']
    if not isinstance(budget, int) or isinstance(budget, bool) or not 1 <= budget <= model['max_tokens']:
        raise ValueError('Repair budget must be positive and no higher than the original budget')
    model['max_tokens'] = budget
    request = build_request(model, previous['requests'][key]['messages'], text, sites)
    paths = [*FILES, folder / 'run.json', folder / 'input_sha256.json', folder / 'full_output.schema.json']
    for saved in previous['result_files'].values():
        paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    return design, previous, model, request, document, schema, sites, metadata, hashes


def render(run):
    row = run['results'].get('enum_repair', {})
    lines = ['# V2 public-schema enum repair', '',
             f"Protocol {run['audit_protocol_version']}; state {run['status']}; model {run['model_id']}.",
             f"Case: {run['case']}. At most one new inference request; no automatic retries.", '',
             f"- Original schema errors: {len(run['sites'])}",
             f"- Repair outcome: {row.get('status', 'pending')}",
             f"- Model-authored patch operations: {row.get('patch_operations')}",
             f"- Schema conformant after repair: {row.get('schema_conformant')}",
             f"- Public identity preserved: {row.get('metadata_conformant')}",
             f"- Completion tokens: {(row.get('usage') or {}).get('completion_tokens')}", '',
             'This is a new post-hoc intervention on a saved output, not its original score.',
             'Enum changes may change the stated topology or policy requirements. They are not assumed to preserve semantics.',
             'No workflow execution, contract-closure claim, or G6-Assert score. Original v1 and earlier audit outputs remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying the saved full-IR response and deriving public enum feedback...', flush=True)
    design, previous, model, request, document, schema, sites, metadata, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'model': previous['model_id'], 'case': previous['case'], 'enum_error_paths': list(sites),
                          'maximum_new_inference_requests': 1, 'requested_max_tokens': model['max_tokens'],
                          'automatic_retries': 0, 'semantic_execution': False}, indent=2))
        return 0
    secret = os.environ.get(model['api_key_env'])
    if not secret:
        raise ValueError('Set ' + model['api_key_env'] + ' in your terminal')
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if (run['input_fingerprint'] != controls.fingerprint(hashes) or run['request'] != request
                or run['model_config'] != model or run['design'] != design):
            raise ValueError('Repair design/code/inputs changed; cannot resume')
        generation.verify_completed(run)
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_enum_repair__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
               'design': design, 'case': previous['case'], 'model_id': previous['model_id'], 'model_config': model,
               'request': generation.transport.sanitize(request, secret), 'sites': sites,
               'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
               'results': {}, 'result_files': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        for path in FILES:
            target = output / 'implementation' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    run['status'] = 'running'
    controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS), str(generation.TESTS)],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        print('verification_failed: ' + str(output / 'verification.txt'), flush=True)
        return 1
    if 'enum_repair' not in run['results']:
        parent.verify_hashes(output, run)
        attempt = output / 'cells/enum_repair'
        row = execute(attempt, request, model, secret, document, schema, sites, metadata)
        controls.write_json(attempt / 'result.json', row)
        run['results']['enum_repair'] = row
        run['result_files']['enum_repair'] = generation.output_checkpoint(attempt)
        controls.write_json(output / 'run.json', run)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    bad = run['results']['enum_repair']['status'] in ('inference_error', 'interrupted_outcome_unknown')
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if bad else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
