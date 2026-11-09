#!/usr/bin/env python3
"""Offline binding-derived assembly; no model call, workflow, or semantic score."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_contract_repair as contract
import binding_assembly

generation, audit = contract.generation, contract.audit
controls, replay, parent = contract.controls, contract.replay, contract.parent
CONFIG = ROOT / 'audit/v2/binding_assembly.json'
POLICY = ROOT / 'audit/v2/assembly_policy.json'
TESTS = ROOT / 'tests/unit/test_v2_binding_assembly.py'
FILES = [Path(__file__).resolve(), CONFIG, POLICY, TESTS, ROOT / 'audit/v2/binding_assembly.py', ROOT / 'audit/v2/BINDING_ASSEMBLY.md']


def input_readiness(inspection):
    context = inspection['context']
    bound = len(inspection['analysis']['external_inputs'])
    unresolved = len(inspection['unresolved_bound_input_links'])
    return {'bound_external_input_count': bound, 'unresolved_bound_input_count': unresolved,
            'resolved_bound_input_fraction': (bound - unresolved) / bound if bound else None,
            'explicit_fixture_link_count': len(context['artifact_fixture_links']),
            'state': ('not_established_no_bound_external_inputs' if not bound else
                      'unresolved_bound_inputs' if unresolved else 'bound_files_resolved_roles_not_verified'),
            'scope': 'File-link presence does not establish input-role correctness or complete source coverage.'}


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('No inference allowed')
    root = ROOT / design['parent_repair']
    saved = replay.read_json(root / 'run.json')
    if saved['status'] != 'complete' or saved.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged model-patch evidence required')
    hashes = parent.verify_hashes(root, saved)
    generation.verify_completed(saved)
    # Verify the earlier enum patch and its public workspace independently.
    _, previous, _, before_patch, _, schema, workspace, context, manifest, older = audit.prepare()
    if previous['case'] != saved['case'] or previous['model_id'] != saved['model_id']:
        raise ValueError('Parent identity mismatch')
    if any(k in hashes and hashes[k] != v for k, v in older.items()):
        raise ValueError('Parent fingerprint conflict')
    hashes.update(older)
    attempt = root / 'cells/contract_repair'
    response = replay.read_json(attempt / 'model_patch.json')
    source = replay.read_json(attempt / 'candidate_ir.json')
    if contract.apply_response(before_patch, response) != source or audit.repair.errors(source, schema):
        raise ValueError('Saved model patch/candidate reproduction failed')
    policy = replay.read_json(POLICY)
    if policy['policy_version'] != 'v2-explicit-binding-assembly/1':
        raise ValueError('Unsupported assembly policy')
    required = {'kind': 'artifact', 'data_type': 'status', 'media_type': 'application/json',
                'role': 'status', 'sensitivity': 'internal', 'persistence': 'workflow'}
    if policy['status_declaration_metadata'] != required:
        raise ValueError('Diagnostic declaration metadata changed; needs a new policy version')
    paths = [*FILES, root / 'run.json', root / 'input_sha256.json']
    for completed in saved['result_files'].values():
        paths.extend(Path(completed['path']).parent / name for name in completed['files'])
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    return design, saved, source, schema, workspace, context, manifest, policy, hashes


def evaluate(source, schema, workspace, context, manifest, policy):
    catalog = generation.census.Catalog()
    getter = lambda service, version: catalog.get(workspace, service, version)
    candidate, decision = binding_assembly.assemble(source, getter, policy)
    schema_errors = audit.repair.errors(candidate, schema)
    if schema_errors:
        raise ValueError('Derived candidate failed the original IR schema; do not promote it')
    before = contract.inspect_candidate(source, schema, workspace, context, manifest)
    after = contract.inspect_candidate(candidate, schema, workspace, context, manifest)
    return candidate, {'assembly': decision, 'before': before, 'after': after,
                       'input_readiness_before': input_readiness(before), 'input_readiness_after': input_readiness(after),
                       'hard_findings_before': len(audit.non_schema_hard(before['analysis']['findings'])),
                       'hard_findings_after': len(audit.non_schema_hard(after['analysis']['findings'])),
                       'protected_model_decisions_preserved': True,
                       'semantic_outcome': 'not_measured', 'execution_ready': False,
                       'note': 'Assembly-policy metadata and canonical-list projection are new declared v2 interventions, not lossless recovery of the original IR.'}


def render(run, result):
    operations = result['assembly']['operations']
    added = sum(op['rule'] == 'declare_existing_model_bound_status' for op in operations)
    projected = sum(op['rule'] == 'project_intent_list_from_existing_port_bindings' for op in operations)
    return '\n'.join(['# V2 offline binding-derived assembly', '',
        f"Protocol {run['audit_protocol_version']}; state {run['status']}; case {run['case']}.",
        'Zero API calls, zero workflow executions, no semantic score.', '',
        f"- Assembly outcome: {result['assembly']['state']}",
        f"- New declarations for existing unused status bindings: {added}",
        f"- Intent lists projected from existing port bindings: {projected}",
        f"- Checked non-schema findings before: {result['hard_findings_before']}",
        f"- Checked non-schema findings after: {result['hard_findings_after']}",
        f"- Existing business artifacts and port bindings preserved: {result['protected_model_decisions_preserved']}",
        f"- Bound external input count: {result['input_readiness_after']['bound_external_input_count']}",
        f"- Input readiness: {result['input_readiness_after']['state']}", '',
        'Zero unresolved bound-file links with zero bound external inputs is not complete input coverage (fraction remains null).',
        'New report declarations contain metadata only, not fabricated report contents or business values.',
        'Real source mappings, operation/runtime semantics, and reference controls are still required before semantic execution.',
        'Original outputs, v1 results, and submitted paper remain unchanged.', ''])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying the saved patch and explicit assembly policy (offline)...', flush=True)
    design, previous, source, schema, workspace, context, manifest, policy, hashes = prepare()
    catalog = generation.census.Catalog()
    planned, decision = binding_assembly.assemble(source, lambda s, v: catalog.get(workspace, s, v), policy)
    if audit.repair.errors(planned, schema):
        raise ValueError('Planned assembly fails the original schema')
    if args.dry_run:
        print(json.dumps({'case': previous['case'], 'model': previous['model_id'], 'verified_inputs': len(hashes),
                          'assembly_state': decision['state'], 'planned_operations': len(decision['operations']),
                          'api_requests': 0, 'workflow_executions': 0, 'semantic_scores': False}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/outputs' / f'package_v2_binding_assembly__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'case': previous['case'], 'model_id': previous['model_id'],
           'input_fingerprint': controls.fingerprint(hashes), 'environment': controls.environment(),
           'status': 'running', 'result_files': {}}
    controls.write_json(output / 'run.json', run)
    controls.write_json(output / 'input_sha256.json', hashes)
    for path in FILES:
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
    candidate, result = evaluate(source, schema, workspace, context, manifest, policy)
    evidence = output / 'evidence'
    controls.write_json(evidence / 'derived_candidate_ir.json', candidate)
    controls.write_json(evidence / 'result.json', result)
    run['result_files']['assembly'] = generation.output_checkpoint(evidence)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    inspection_errors = any(f['category'] == 'inspection_error'
        for stage in ('before', 'after') for f in result[stage]['analysis']['findings'])
    blocked = result['assembly']['state'] == 'blocked_no_changes'
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if inspection_errors or blocked else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, result))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
