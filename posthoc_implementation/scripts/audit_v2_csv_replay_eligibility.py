#!/usr/bin/env python3
"""Preserve 108 cells; inspect saved CSV/PostgreSQL replay prerequisites only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import io
import itertools
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'audit/v2'))
import run_v2_csv_postgres_controls as previous
import csv_replay_eligibility as analysis

controls, replay = previous.controls, previous.replay
CONFIG = ROOT / 'audit/v2/csv_replay_eligibility.v1.json'
TESTS = ROOT / 'tests/unit/test_v2_csv_replay_eligibility.py'
DOC = ROOT / 'audit/v2/CSV_REPLAY_ELIGIBILITY.md'


def local_schema(schema):
    todo = [schema]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            for name in ('$ref', '$dynamicRef'):
                if name in node and (not isinstance(node[name], str) or not node[name].startswith('#')):
                    raise ValueError('Nonlocal IR schema reference; no network resolution allowed')
            todo.extend(node.values())
        elif isinstance(node, list): todo.extend(node)
    analysis.Draft202012Validator.check_schema(schema)


def verify_roster(sources, config):
    expected = set(itertools.product(config['models'], config['methods'], config['cases'], config['samples']))
    actual = []
    for source in sources:
        identity = (source['model'], source['method'], source['case'], source['sample_index'])
        if source['id'] != '/'.join(map(str, identity)): raise ValueError('Cell identity differs')
        if source['route'] != ('direct_argo' if source['method'] in ('m0', 'm1', 'm2') else 'serviceflow_ir'):
            raise ValueError('Cell route differs')
        actual.append(identity)
    if len(actual) != config['expected_cells'] or len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('Missing, duplicate or undeclared original cells')
    if Counter(s['route'] for s in sources) != config['expected_routes']: raise ValueError('Route counts differ')


def prepare():
    design = replay.read_json(CONFIG)
    root = ROOT / design['controls_run']; run = replay.read_json(root / 'run.json')
    hashes = previous.coverage.frozen.parent.verify_hashes(root, run)
    if run['status'] != 'complete' or run.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged PostgreSQL controls required')
    if {c['case'] for c in run['case_results']} != set(design['cases']) or not all(c['control_gate_pass'] for c in run['case_results']):
        raise ValueError('Both reference control gates must have passed')
    seal_path = ROOT / design['controls_review_seal']; seal = replay.read_json(seal_path)
    if Path(seal['run_directory']).resolve() != root.resolve() or controls.fingerprint(seal['files']) != seal['output_fingerprint']:
        raise ValueError('Review output seal differs')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(seal['files']): raise ValueError('Reviewed control output roster differs')
    extra = [Path(__file__).resolve(), Path(analysis.__file__), CONFIG, TESTS, DOC, seal_path,
             root / 'run.json', root / 'input_sha256.json']
    for relative, sha in seal['files'].items():
        path = analysis.safe(root, relative)
        if controls.sha256(path) != sha: raise ValueError('Reviewed control output changed: ' + relative)
        extra.append(path)
    census = ROOT / design['census_run']; old = replay.read_json(census / 'run.json')
    if old['status'] != 'complete' or old.get('source_inputs_unchanged') is not True: raise ValueError('Completed original census required')
    extra += [census / 'run.json', census / 'input_sha256.json']
    baseline = ROOT / run['design']['coverage_run']
    coverage_run = replay.read_json(baseline / 'run.json')
    public_root = ROOT / coverage_run['design']['public_baseline']
    sources, contexts = [], {}
    for case in design['cases']:
        saved = old['completed_cases'][case]; path = Path(saved['path'])
        if controls.sha256(path) != saved['sha256']: raise ValueError('Census checkpoint changed')
        record = replay.read_json(path)
        if record['reference']['case'] != case: raise ValueError('Census case differs')
        extra.append(path)
        workspace = public_root / case / 'public_workspace' / case
        schema_path = workspace / 'schemas/serviceflow_ir.schema.json'
        schema = replay.read_json(schema_path); local_schema(schema)
        contract_path = root / 'cases' / case / 'public_fixture/contract.json'
        contract = replay.read_json(contract_path)
        contexts[case] = {'workspace': workspace, 'schema': schema, 'contract': contract}
        extra += [schema_path, contract_path, workspace / 'workspace.yaml']
        for cell in record['model_cells']:
            source = cell['source']; artifact = Path(source['artifact'])
            digest = controls.sha256(artifact) if artifact.is_file() else 'MISSING'
            if digest != cell.get('artifact_sha256', 'MISSING'): raise ValueError('Original saved artifact changed: ' + source['id'])
            sources.append(source)
            for file in [artifact, Path(source['manifest'])]:
                name = str(file.resolve()); sha = controls.sha256(file) if file.is_file() else 'MISSING'
                if name in hashes and hashes[name] != sha: raise ValueError('Original saved source differs: ' + name)
                hashes[name] = sha
    verify_roster(sources, design)
    source_map = {s['id']: s for s in sources}
    sources = [source_map['/'.join(map(str, values))] for values in itertools.product(design['models'], design['methods'], design['cases'], design['samples'])]
    for path in extra:
        name, sha = str(path.resolve()), controls.sha256(path)
        if name in hashes and hashes[name] != sha: raise ValueError('Pinned evidence differs: ' + name)
        hashes[name] = sha
    return {'design': design, 'sources': sources, 'contexts': contexts, 'hashes': hashes}


def inspect(source, prepared):
    path = Path(source['artifact'])
    sha = controls.sha256(path) if path.is_file() else 'MISSING'
    documents, error = analysis.read_saved(path, prepared['design']['max_document_bytes'], prepared['design']['max_document_nodes'])
    if error:
        checked = {'state': error, 'execution_ready': False, 'semantic_outcome': 'not_measured', 'findings': []}
    elif source['route'] == 'direct_argo': checked = analysis.direct_inventory(documents)
    elif len(documents) != 1:
        checked = {'state': 'multiple_ir_documents', 'execution_ready': False, 'semantic_outcome': 'not_measured',
            'findings': [{'category': 'saved_structure', 'code': 'multiple_ir_documents', 'subject': 'document'}]}
    else:
        context = prepared['contexts'][source['case']]
        checked = analysis.analyze_ir(documents[0], context['workspace'], context['contract'], context['contract']['source_csv_sha256'], context['schema'])
    checked.setdefault('semantic_outcome', 'not_measured')
    if (controls.sha256(path) if path.is_file() else 'MISSING') != sha: raise ValueError('Saved artifact changed during inspection')
    return {'source': source, 'artifact_sha256': sha, 'analysis': checked}


def render(output, run, rows):
    groups = []
    for model, method in itertools.product(run['design']['models'], run['design']['methods']):
        selected = [r for r in rows if r['source']['model'] == model and r['source']['method'] == method]
        ir = method in ('m3', 'm4', 'm5')
        groups.append({'model': model, 'method': method, 'route': 'serviceflow_ir' if ir else 'direct_argo',
            'declared': 6, 'recorded': len(selected), 'present': sum(r['artifact_sha256'] != 'MISSING' for r in selected),
            'static_contract_matches': sum(r['analysis'].get('static_contract_match', False) for r in selected) if ir else None,
            'runtime_intervention_only_candidates': sum(r['analysis']['state'] == 'runtime_intervention_candidate_pending_design' for r in selected) if ir else None})
    ir_rows = [r for r in rows if r['source']['route'] == 'serviceflow_ir']
    codes = Counter((f['category'], f['code']) for r in ir_rows for f in r['analysis'].get('findings', []))
    summary = {'declared': len(run['sources']), 'recorded': len(rows),
        'routes': dict(Counter(r['source']['route'] for r in rows)),
        'states': dict(Counter(r['analysis']['state'] for r in rows)), 'by_model_method': groups,
        'finding_codes': [{'category': c, 'code': k, 'findings': n} for (c, k), n in sorted(codes.items())],
        'execution_ready': 0, 'llm_calls': 0, 'workflow_executions': 0, 'semantic_scores': 0}
    controls.write_json(output / 'eligibility.json', rows); controls.write_json(output / 'aggregate.json', summary)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['cell', 'model', 'method', 'case', 'sample', 'route', 'original_method_status', 'state', 'artifact_present', 'finding_codes', 'execution_ready'])
    writer.writeheader()
    for row in rows:
        source, a = row['source'], row['analysis']
        writer.writerow({'cell': source['id'], **{k: source[k] for k in ('model', 'method', 'case', 'route')},
            'sample': source['sample_index'], 'original_method_status': source.get('original_method_status'),
            'state': a['state'], 'artifact_present': row['artifact_sha256'] != 'MISSING',
            'finding_codes': json.dumps([f['code'] for f in a.get('findings', [])]), 'execution_ready': False})
    (output / 'eligibility.csv').write_text(stream.getvalue())
    lines = ['# Saved CSV/PostgreSQL output eligibility audit', '',
        f"Protocol {run['design']['protocol_version']}; status {run['status']}; recorded {len(rows)}/{len(run['sources'])} declared cells.",
        'Zero model calls, workflow/database executions, repairs and new semantic scores. Original statuses and outputs are preserved.', '',
        '| State | Cells |', '|---|---:|']
    lines.extend(f'| {k} | {v} |' for k, v in sorted(summary['states'].items()))
    lines += ['', '## Model/method coverage', '',
        '| Model | Method | Route | Declared | Present | Static contract match | Runtime-intervention-only candidate |',
        '|---|---|---|---:|---:|---:|---:|']
    for g in groups:
        lines.append(f"| {g['model']} | {g['method']} | {g['route']} | {g['declared']} | {g['present']} | {g['static_contract_matches'] if g['static_contract_matches'] is not None else '-'} | {g['runtime_intervention_only_candidates'] if g['runtime_intervention_only_candidates'] is not None else '-'} |")
    lines += ['', '## Overlapping IR findings', '', '| Category | Code | Findings |', '|---|---|---:|']
    lines.extend(f'| {c} | {k} | {n} |' for (c, k), n in sorted(codes.items()))
    lines += ['', 'Static candidates are not execution-ready submissions. No verified IR-to-PostgreSQL execution adapter exists in this phase.',
        'Runtime-intervention candidates hypothetically remove only runtime-interpretation findings; no resource, binding, parameter or missing choice is changed.',
        'Backend-subset and public-context findings are not automatically LLM errors. A declared original catalog feature may be outside the new controlled implementation subset.',
        'Direct-Argo documents retain their separate route; their script bodies are never executed or converted into IR.',
        'See eligibility.json/CSV, original source identities, per-cell checkpoints and input fingerprints.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true'); parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying PostgreSQL reference evidence and all 108 original cell identities (read-only)...', flush=True)
    p = prepare()
    if args.dry_run:
        print(json.dumps({'declared_cells': len(p['sources']), 'routes': p['design']['expected_routes'],
            'cases': p['design']['cases'], 'llm_calls': 0, 'workflow_executions': 0, 'semantic_scores': 0}, indent=2)); return 0
    if args.resume:
        output = args.resume.resolve(); run = replay.read_json(output / 'run.json')
        if run['input_fingerprint'] != controls.fingerprint(p['hashes']) or run['sources'] != p['sources']:
            raise ValueError('Immutable source, implementation or policy differs; cannot resume')
    else:
        output = ROOT / 'audit/outputs' / ('package_v2_csv_replay_eligibility__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        run = {'design': p['design'], 'sources': p['sources'], 'completed_cells': {}, 'input_fingerprint': controls.fingerprint(p['hashes']),
               'llm_calls': 0, 'workflow_executions': 0, 'semantic_scores': 0, 'status': 'running'}
        controls.write_json(output / 'input_sha256.json', p['hashes'])
    controls.write_json(output / 'run.json', run); print('Output: ' + str(output), flush=True)
    tested = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tested.stdout + tested.stderr)
    if tested.returncode: raise ValueError('Eligibility unit checks failed; inspect verification.txt')
    rows = []
    for number, source in enumerate(p['sources']):
        key = source['id']
        if key in run['completed_cells']:
            saved = run['completed_cells'][key]; path = Path(saved['path'])
            if controls.sha256(path) != saved['sha256']: raise ValueError('Completed eligibility checkpoint changed')
            row = replay.read_json(path)
            if row['source'] != source: raise ValueError('Checkpoint identity differs')
        else:
            try: row = inspect(source, p)
            except Exception as exc:
                path = Path(source['artifact'])
                row = {'source': source, 'artifact_sha256': controls.sha256(path) if path.is_file() else 'MISSING',
                       'analysis': {'state': 'inspection_error', 'error_type': type(exc).__name__, 'execution_ready': False,
                                    'semantic_outcome': 'not_measured', 'findings': []}}
            path = output / 'cells' / key / 'eligibility.json'; controls.write_json(path, row)
            run['completed_cells'][key] = {'path': str(path), 'sha256': controls.sha256(path)}
            controls.write_json(output / 'run.json', run)
        rows.append(row); print(f"[{number+1}/108] {key}: {row['analysis']['state']}", flush=True)
    previous.coverage.frozen.parent.verify_hashes(output, run)
    run['source_inputs_unchanged'] = True
    run['status'] = 'complete_with_errors' if any(r['analysis']['state'] == 'inspection_error' for r in rows) else 'complete'
    controls.write_json(output / 'run.json', run); render(output, run, rows)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
