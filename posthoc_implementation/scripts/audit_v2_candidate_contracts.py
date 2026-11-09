#!/usr/bin/env python3
"""Offline contract/input audit of a saved candidate and its restricted patch."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_enum_repair as repair

generation = repair.generation
controls, replay, parent = generation.controls, generation.replay, generation.parent
CONFIG = ROOT / 'audit/v2/candidate_contract_audit.json'
TESTS = ROOT / 'tests/unit/test_v2_candidate_contracts.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/CANDIDATE_CONTRACT_AUDIT.md']


def context_review(document, public_files):
    """Observable input/writer signals, not new catalog rules or semantic scores."""
    artifacts = {a['artifact_id']: a for a in document['artifacts']}
    writers = defaultdict(list)
    reads_external = []
    read_write_reuse = []
    for binding in document['bindings']:
        intent = binding['intent_id']
        inputs = {p['artifact_id'] for p in binding['input_bindings']}
        outputs = {p['artifact_id'] for p in binding['output_bindings']}
        for identity in outputs:
            writers[identity].append(intent)
        for identity in inputs:
            if identity in artifacts and not artifacts[identity].get('producer'):
                reads_external.append({'intent_id': intent, 'artifact_id': identity})
        if inputs & outputs:
            read_write_reuse.append({'intent_id': intent, 'artifact_ids': sorted(inputs & outputs)})
    links = [{'artifact_id': a['artifact_id'], 'fixture_ref': a['fixture_ref']}
             for a in document['artifacts'] if isinstance(a.get('fixture_ref'), str) and a['fixture_ref']]
    fixture_files = sorted(p for p in public_files if p.startswith('fixtures/'))
    cues = []
    if fixture_files and not links:
        cues.append('public_fixtures_available_but_no_artifact_fixture_ref')
    if fixture_files and not reads_external:
        cues.append('no_bound_artifact_with_external_producer')
    return {'artifact_fixture_links': links, 'bound_external_inputs': reads_external,
            'public_fixture_files': fixture_files, 'read_write_reuse': read_write_reuse,
            'multiple_writer_artifacts': {k: v for k, v in sorted(writers.items()) if len(v) > 1},
            'review_cues': cues,
            'scope': 'Absent artifact links do not exclude implicit service inputs. Read/write reuse is not itself a dependency-cycle finding.'}


def non_schema_hard(findings):
    return [f for f in findings if f['category'] in generation.census.analysis.HARD
            and f['code'] != 'ir_schema_violation']


def summarize(before, after, before_context, after_context):
    def counts(a):
        return {'schema_violations': sum(f['code'] == 'ir_schema_violation' for f in a['findings']),
                'non_schema_hard_findings': len(non_schema_hard(a['findings'])),
                'finding_counts': a['finding_counts'],
                'code_counts': dict(Counter(f['code'] for f in a['findings']))}
    unchanged = ([f for f in before['findings'] if f['code'] != 'ir_schema_violation'] ==
                 [f for f in after['findings'] if f['code'] != 'ir_schema_violation'])
    blocked = bool(non_schema_hard(after['findings']))
    return {'before': counts(before), 'after': counts(after), 'non_schema_diagnostics_unchanged': unchanged,
            'input_and_writer_context_unchanged': before_context == after_context,
            'execution_status': 'blocked_by_static_contract_or_dataflow_findings' if blocked else 'requires_runtime_and_input_review',
            'execution_ready': False, 'semantic_outcome': 'not_measured', 'public_gates': 'not_remeasured'}


def prepare():
    design = replay.read_json(CONFIG)
    if design['maximum_inference_requests'] != 0:
        raise ValueError('This audit permits no inference')
    root = ROOT / design['parent_repair']
    previous = replay.read_json(root / 'run.json')
    if previous['status'] != 'complete' or previous.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged repair evidence required')
    hashes = parent.verify_hashes(root, previous)
    generation.verify_completed(previous)
    generation_root = ROOT / previous['design']['parent_generation']
    original = replay.read_json(generation_root / 'run.json')
    checked = parent.verify_hashes(generation_root, original)
    generation.verify_completed(original)
    if any(k in hashes and hashes[k] != v for k, v in checked.items()):
        raise ValueError('Parent fingerprints disagree')
    hashes.update(checked)
    if (original['case'] != previous['case'] or original['model_id'] != previous['model_id']
            or previous['results']['enum_repair']['status'] != 'schema_repaired'):
        raise ValueError('Expected a successful schema repair of this source')
    source = generation_root / 'cells' / previous['design']['condition'] / 'assistant_content.txt'
    before = generation.compact_ir.strict_json(source.read_text())
    attempt = root / 'cells/enum_repair'
    patch = replay.read_json(attempt / 'patch.json')
    after = replay.read_json(attempt / 'candidate_ir.json')
    schema = replay.read_json(generation_root / 'full_output.schema.json')
    sites = repair.enum_sites(before, schema)
    if repair.apply_patch(before, patch, sites) != after or repair.errors(after, schema):
        raise ValueError('Saved patch does not reproduce the schema-conformant candidate')
    if not all(after[k] == before[k] == original['metadata'][k] for k in generation.compact_ir.BOOKKEEPING):
        raise ValueError('Public identity changed')
    inventory_file = ROOT / replay.read_json(parent.CONFIG)['inventory_run'] / 'run.json'
    inventory = replay.read_json(inventory_file)
    workspace = Path(inventory['control_directory']) / 'cases' / original['case'] / 'public_workspace' / original['case']
    context = generation.census.public_context(workspace)
    manifest = controls.load(workspace / 'workspace.yaml')
    generation.verify_prompt_inventory(workspace, manifest)
    if controls.load(workspace / 'schemas/serviceflow_ir.schema.json') != schema:
        raise ValueError('Public schema differs from the saved generation schema')
    paths = [*FILES, repair.TESTS, root / 'run.json', root / 'input_sha256.json',
             generation_root / 'run.json', generation_root / 'input_sha256.json',
             generation_root / 'full_output.schema.json', inventory_file, workspace / 'workspace.yaml']
    for run in (previous, original):
        for saved in run['result_files'].values():
            paths.extend(Path(saved['path']).parent / name for name in saved['files'])
    paths.extend(workspace / entry['path'] for entry in manifest['files'])
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    return design, previous, before, after, patch, schema, workspace, context, manifest, hashes


def inspect(document, schema, workspace, context, catalog):
    return generation.census.analysis.analyze(document, schema=schema,
        catalog_get=lambda service, version: catalog.get(workspace, service, version),
        workspace=workspace, scenarios=context['scenarios'], load=controls.load)


def render(run, result):
    before, after = result['before'], result['after']
    context = result['after_context']
    lines = ['# V2 candidate contract/input audit', '',
             f"Protocol {run['audit_protocol_version']}; state {run['status']}; case {run['case']}.",
             'Offline inspection only: zero API requests and zero workflow executions.', '',
             '| Check | Before enum repair | After enum repair |', '|---|---:|---:|',
             f"| Schema violations | {before['schema_violations']} | {after['schema_violations']} |",
             f"| Other checked contract/dataflow findings | {before['non_schema_hard_findings']} | {after['non_schema_hard_findings']} |",
             f"| Explicit artifact fixture links | {len(result['before_context']['artifact_fixture_links'])} | {len(context['artifact_fixture_links'])} |", '',
             f"Non-schema diagnostics unchanged: {result['non_schema_diagnostics_unchanged']}.",
             f"Input/writer context unchanged: {result['input_and_writer_context_unchanged']}.",
             f"Execution status: {result['execution_status']}.", '', '## Checked contract/dataflow findings', '']
    for finding in result['hard_findings_after']:
        lines.append(f"- {finding['code']}: `{finding['subject']}`")
    lines += ['', '## Input and runtime review cues', '']
    lines.extend('- ' + cue for cue in context['review_cues'])
    lines += [f"- Bindings reusing an artifact for both input/output: {len(context['read_write_reuse'])}.",
              '- Other static categories remain in the detailed analyses; context signals are not automatic semantic failures.', '',
              'The patch fixed schema enum errors only. It did not establish contract closure, correct inputs, or G6-Assert success.',
              'Do not invent fixture inputs, rewrite graph edges, or replace runtime outputs using expected answers.',
              'Original model outputs, v1 scores, submitted paper, and earlier audit evidence remain unchanged.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    print('Verifying saved patch, public workspace, and parent evidence (offline)...', flush=True)
    design, previous, before, after, patch, schema, workspace, context, manifest, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'case': previous['case'], 'model': previous['model_id'], 'verified_inputs': len(hashes),
                          'verified_model_patch_operations': len(patch), 'api_requests': 0,
                          'workflow_executions': 0, 'semantic_scores': False}, indent=2))
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/outputs' / f'package_v2_candidate_contracts__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    run = {'package_version': design['package_version'], 'audit_protocol_version': design['audit_protocol_version'],
           'design': design, 'model_id': previous['model_id'], 'case': previous['case'],
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
    catalog = generation.census.Catalog()
    a = inspect(before, schema, workspace, context, catalog)
    b = inspect(after, schema, workspace, context, catalog)
    if a['state'] != 'inspected' or b['state'] != 'inspected':
        raise ValueError('Candidate inspection did not complete')
    files = [entry['path'] for entry in manifest['files']]
    ca, cb = context_review(before, files), context_review(after, files)
    result = summarize(a, b, ca, cb)
    result.update(before_context=ca, after_context=cb, hard_findings_after=non_schema_hard(b['findings']))
    evidence = output / 'evidence'
    controls.write_json(evidence / 'before_analysis.json', a)
    controls.write_json(evidence / 'after_analysis.json', b)
    controls.write_json(evidence / 'verified_patch.json', patch)
    controls.write_json(evidence / 'result.json', result)
    run['result_files']['contract_audit'] = generation.output_checkpoint(evidence)
    try:
        parent.verify_hashes(output, run)
        generation.verify_completed(run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    inspection_errors = any(f['category'] == 'inspection_error' for doc in (a, b) for f in doc['findings'])
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if inspection_errors else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, result))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
