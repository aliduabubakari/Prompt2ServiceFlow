#!/usr/bin/env python3
"""Read-only static coverage of original workflows and saved M0-M5 artifacts."""
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
import run_v2_family_controls as family
import coverage_analysis as analysis

controls, replay, parent = family.controls, family.replay, family.parent
CONFIG = ROOT / 'audit/v2/coverage_planner.json'
TESTS = ROOT / 'tests/unit/test_v2_coverage_planner.py'
FILES = list(dict.fromkeys([Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/coverage_analysis.py',
                           ROOT / 'audit/v2/COVERAGE_PLANNER.md', ROOT / 'scripts/run_v2_family_controls.py', *family.FILES]))


def collect_cells(inventory, batches, methods):
    cases = {s['case'] for s in inventory['sources'] if s['kind'] == 'reference'}
    sources, identities = [], set()
    for batch in batches:
        document = replay.read_json(batch)
        if document.get('expected_cell_count', len(document['runs'])) != len(document['runs']):
            raise ValueError('Original batch does not contain all its declared cells')
        for observation in document['runs']:
            method = observation['method']
            if method not in methods:
                continue
            case = observation['split'] + '/' + observation['instance']
            identity = (observation['model'], method, case, observation['sample_index'])
            if identity in identities or case not in cases:
                raise ValueError('Duplicate or unknown immutable model cell')
            identities.add(identity)
            manifest = Path(observation['manifest_path']).resolve()
            if not manifest.is_relative_to(batch.parent.resolve()):
                raise ValueError('Source manifest escapes its declared batch')
            metadata = replay.read_json(manifest)
            if (metadata.get('method', {}).get('id') != method or metadata.get('model', {}).get('model_id') != identity[0]
                    or metadata.get('instance', {}).get('id') != observation['instance']
                    or metadata.get('instance', {}).get('split') != observation['split']
                    or metadata.get('sample_index') != identity[-1]):
                raise ValueError('Source manifest and declared cell identity disagree')
            direct = method in ('m0', 'm1', 'm2')
            artifact = (manifest.parent / 'argo_generated/workflow.yaml' if direct else
                        replay.selected_ir(manifest.parent, method))
            if not artifact.resolve().is_relative_to(batch.parent.resolve()):
                raise ValueError('Saved artifact escapes its declared batch')
            sources.append({'id': '/'.join(map(str, identity)), 'model': identity[0], 'method': method,
                            'case': case, 'sample_index': identity[-1], 'manifest': str(manifest),
                            'artifact': str(artifact), 'route': 'direct_argo' if direct else 'serviceflow_ir',
                            'original_method_status': metadata.get('method_status', metadata.get('driver_status'))})
    return sources


def inspect_argo(path, max_bytes):
    if not path.is_file():
        return {'state': 'missing_artifact', 'route': 'direct_argo', 'execution_ready': False}
    if path.stat().st_size > max_bytes:
        return {'state': 'inspection_limit', 'route': 'direct_argo', 'execution_ready': False}
    try:
        documents = list(controls.yaml.safe_load_all(path.read_text()))
        if not documents or any(not isinstance(d, dict) for d in documents):
            raise ValueError('Expected YAML resource objects')
        images, script_count, container_count = set(), 0, 0
        for doc in documents:
            for value in analysis.walk(doc):
                if isinstance(value, dict):
                    if isinstance(value.get('image'), str):
                        images.add(value['image'])
                    script_count += isinstance(value.get('script'), dict)
                    container_count += isinstance(value.get('container'), dict)
        return {'state': 'direct_artifact_inventoried', 'route': 'direct_argo',
                'resource_kinds': sorted({str(d.get('kind', 'unspecified')) for d in documents}),
                'images': sorted(images), 'script_templates': script_count, 'container_templates': container_count,
                'execution_ready': False, 'readiness_note': 'Requires a separate direct-Argo/code execution route; no IR conversion, code execution, or validity claim'}
    except Exception as exc:
        return {'state': 'direct_parse_or_shape_error', 'route': 'direct_argo', 'error_type': type(exc).__name__, 'execution_ready': False}


def inspect_ir(path, workspace, catalog, maximum):
    document, error = analysis.read_document(path, controls.load, maximum)
    if error:
        return {'state': error, 'execution_ready': False, 'services': [], 'missing_services': [], 'service_roster_complete': False}
    return analysis.analyze_ir(document, workspace, catalog, controls.load, replay._fixture_scenarios(workspace))


def case_record(case, sources, baseline, catalog, maximum):
    workspace = baseline / 'cases' / case / 'public_workspace' / case
    reference = controls.BENCHMARK / 'instances' / case / 'gold/serviceflow.yaml'
    reference_record = {'case': case, 'reference_ir_sha256': controls.sha256(reference),
                        'analysis': inspect_ir(reference, workspace, catalog, maximum),
                        'role': 'reference-side implementation planning only, not model repair input'}
    records = []
    for source in sources:
        path = Path(source['artifact'])
        result = inspect_argo(path, maximum) if source['route'] == 'direct_argo' else inspect_ir(path, workspace, catalog, maximum)
        records.append({'source': source, 'artifact_sha256': controls.sha256(path) if path.is_file() else 'MISSING', 'analysis': result})
    return {'reference': reference_record, 'model_cells': records}


def summarize(records, cohort_size):
    references, cells, service_backlog = [], [], defaultdict(lambda: {'reference_cases': set(), 'model_cells': set(), 'catalog_states': set()})
    for record in records:
        references.append(record['reference'])
        cells.extend(record['model_cells'])
        for key in record['reference']['analysis'].get('missing_services', []):
            service_backlog[key]['reference_cases'].add(record['reference']['case'])
            service_backlog[key]['catalog_states'].update(s.get('catalog_state', 'not_inspected') for s in record['reference']['analysis'].get('services', []) if s['service'] == key)
        for cell in record['model_cells']:
            for key in cell['analysis'].get('missing_services', []):
                service_backlog[key]['model_cells'].add(cell['source']['id'])
                service_backlog[key]['catalog_states'].update(s.get('catalog_state', 'not_inspected') for s in cell['analysis'].get('services', []) if s['service'] == key)
    proposals = analysis.propose_cohorts(references, cohort_size)
    # Availability is reported AFTER ranking. It never affects cohort selection.
    proposed = set(proposals['tentative_shared_implementation_cohort'])
    candidates = [c for c in cells if c['source']['case'] in proposed]
    proposals['proposed_original_cell_roster'] = [c['source']['id'] for c in candidates]
    return {'reference_pipeline_count': len(references), 'original_model_cell_count': len(cells),
            'routes': dict(Counter(c['source']['route'] for c in cells)),
            'cell_states': dict(Counter(c['analysis']['state'] for c in cells)),
            'service_roster_complete_ir_cells': sum(c['source']['route'] == 'serviceflow_ir' and c['analysis'].get('service_roster_complete', False) for c in cells),
            'execution_ready_cells': 0, 'readiness_note': 'No original-IR translator or direct-Argo execution path is certified by static analysis',
            'proposals': proposals,
            'service_backlog': {k: {'reference_cases': sorted(v['reference_cases']), 'model_cells': sorted(v['model_cells']),
                                    'catalog_states': sorted(v['catalog_states']),
                                    'next_review': 'registered_service_adapter_gap' if v['catalog_states'] == {'public_descriptor_present'} else
                                                   'catalog_or_binding_review_before_considering_implementation'}
                                for k, v in sorted(service_backlog.items())}}


def render(run, combined, records):
    lines = ['# Original-corpus offline replay coverage plan', '',
             f"Package {run['package_version']}; audit protocol {run['audit_protocol_version']}; state {run['status']}.",
             'Static inspection only: zero LLM calls and zero saved-code/workflow executions. Not semantic scores.', '',
             f"Original pipelines analyzed: {combined['reference_pipeline_count']}; saved model cells retained: {combined['original_model_cell_count']}.",
             f"Service-roster-complete IR cells: {combined['service_roster_complete_ir_cells']}; certified execution-ready cells: 0.", '',
             'A complete service roster is only an upper bound; input, schema, resource, and graph translation still require verification.', '',
             '## Saved artifact coverage', '', '| Route/state | Count |', '|---|---:|']
    lines.extend(f'| route: {k} | {v} |' for k, v in sorted(combined['routes'].items()))
    lines.extend(f'| state: {k} | {v} |' for k, v in sorted(combined['cell_states'].items()))
    lines += ['', '## Reference-side implementation shortlist', '',
              'Ranking uses missing capabilities and interface/resource flags, never model success or semantic scores.',
              'Counts are workload proxies, not development-time estimates. Deletion and network flags require review.', '',
              '| Pipeline | Missing service/version pairs | Control gaps | Input gaps | Network/credential review | Deletion review |', '|---|---:|---:|---:|---:|---:|']
    refs = {r['reference']['case']: r['reference']['analysis'] for r in records}
    for case in combined['proposals']['reference_ranking'][:12]:
        a = refs[case]
        lines.append(f"| {case} | {len(a['missing_services'])} | {a.get('issue_counts', {}).get('control', 0)} | {a.get('issue_counts', {}).get('input', 0)} | {len(a.get('network_required_services', [])) + len(a.get('credential_review_services', []))} | {len(a.get('destructive_review_services', []))} |")
    lines += ['', '## Tentative shared-implementation cohort', '',
              'Proposal for human review, not an authorization to execute or a frozen confirmatory selection.']
    lines.extend('- ' + c for c in combined['proposals']['tentative_shared_implementation_cohort'])
    if not combined['proposals']['conservative_local_shortlist']:
        lines.append('No reference meets all conservative local/no-deletion/no-missing-input screening criteria.')
    lines += ['', 'See pipeline_coverage.json, saved_cell_coverage.json, service_backlog.json, and cohort_proposals.json for complete evidence.',
              'Reference IR is used only to describe required implementations; it must never replace model bindings.',
              'M0–M2 are inventoried as direct Argo/code, not converted to IR or declared comparable new full passes.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    policy = replay.read_json(CONFIG)
    parent_root = ROOT / policy['parent_family_run']
    print('Checking immutable family-control evidence and original source inventory...', flush=True)
    previous = replay.read_json(parent_root / 'run.json')
    if previous['status'] != 'complete' or not previous['source_inputs_unchanged'] or previous['environment'] != controls.environment():
        raise ValueError('Completed unchanged family controls in the same environment are required')
    hashes = parent.verify_hashes(parent_root, previous)
    prior_replay = replay.read_json(ROOT / replay.read_json(family.CONFIG)['parent_replay'] / 'run.json')
    inventory_root = Path(prior_replay['inventory_directory'])
    inventory = replay.read_json(inventory_root / 'run.json')
    baseline = Path(inventory['control_directory'])
    cases = sorted({s['case'] for s in inventory['sources'] if s['kind'] == 'reference'})
    if len(cases) != policy['expected_original_pipelines']:
        raise ValueError('Original pipeline roster differs from the protocol')
    batches = [Path(p) for p in inventory['batches']]
    sources = collect_cells(inventory, batches, policy['methods'])
    if args.dry_run:
        print(json.dumps({'package_version': policy['package_version'], 'audit_protocol_version': policy['audit_protocol_version'],
                          'original_pipelines': len(cases), 'saved_model_cells': len(sources),
                          'routes': dict(Counter(s['route'] for s in sources)), 'llm_calls': 0, 'workflow_executions': 0}, indent=2))
        return 0
    paths = set([*FILES, parent_root / 'run.json', parent_root / 'input_sha256.json', inventory_root / 'run.json', *batches])
    paths.update(Path(s['artifact']) for s in sources)
    paths.update(Path(s['manifest']) for s in sources)
    hashes.update({str(p.resolve()): controls.sha256(p) if p.is_file() else 'MISSING' for p in paths})
    fingerprint = controls.fingerprint(hashes)
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if run['input_fingerprint'] != fingerprint or run['sources'] != sources:
            raise ValueError('Planner code, sources, or immutable selection changed')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_coverage__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': policy['package_version'], 'audit_protocol_version': policy['audit_protocol_version'],
               'input_fingerprint': fingerprint, 'environment': controls.environment(), 'llm_calls': 0,
               'workflow_executions': 0, 'sources': sources, 'completed_cases': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        for path in FILES:
            target = output / 'implementation' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    run['status'] = 'running'
    controls.write_json(output / 'run.json', run)
    print(f'Output: {output}', flush=True)
    test = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(test.stdout + test.stderr)
    if test.returncode:
        run['status'] = 'verification_failed'
        controls.write_json(output / 'run.json', run)
        raise ValueError('Planner verification failed; inspect verification.txt')
    catalog = analysis.Catalog(controls.load)
    grouped = defaultdict(list)
    for source in sources:
        grouped[source['case']].append(source)
    for number, case in enumerate(cases):
        if case in run['completed_cases']:
            continue
        try:
            record = case_record(case, grouped[case], baseline, catalog, policy['max_document_bytes'])
        except Exception as exc:
            record = {'reference': {'case': case, 'analysis': {'state': 'planner_error', 'error_type': type(exc).__name__,
                        'services': [], 'missing_services': [], 'execution_ready': False}},
                      'model_cells': [{'source': s, 'analysis': {'state': 'planner_error', 'error_type': type(exc).__name__}}
                                      for s in grouped[case]]}
        target = output / 'cases' / case / ('attempt_' + uuid.uuid4().hex[:8]) / 'coverage.json'
        controls.write_json(target, record)
        run['completed_cases'][case] = str(target)
        controls.write_json(output / 'run.json', run)
        print(f"[{number+1}/{len(cases)}] {case}: reference={record['reference']['analysis']['state']}; model cells={len(grouped[case])}", flush=True)
    records = [replay.read_json(Path(run['completed_cases'][case])) for case in cases]
    combined = summarize(records, policy['cohort_size'])
    controls.write_json(output / 'pipeline_coverage.json', [r['reference'] for r in records])
    controls.write_json(output / 'saved_cell_coverage.json', [c for r in records for c in r['model_cells']])
    controls.write_json(output / 'service_backlog.json', combined['service_backlog'])
    controls.write_json(output / 'cohort_proposals.json', combined['proposals'])
    controls.write_json(output / 'aggregate_coverage.json', combined)
    try:
        parent.verify_hashes(output, run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    errors = any(r['reference']['analysis']['state'] in ('planner_error', 'inspection_error') or any(c['analysis']['state'] in ('planner_error', 'inspection_error') for c in r['model_cells']) for r in records)
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if errors else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, combined, records))
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
