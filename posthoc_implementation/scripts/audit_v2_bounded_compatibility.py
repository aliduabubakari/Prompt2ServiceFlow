#!/usr/bin/env python3
"""Read-only all-blocker audit of the fixed bounded-window saved-IR cohort."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_bounded_window as previous
import compatibility_analysis as analysis

controls, replay = previous.controls, previous.replay
CONFIG = ROOT / 'audit/v2/bounded_compatibility.json'
TESTS = ROOT / 'tests/unit/test_v2_bounded_compatibility.py'
GUIDE = ROOT / 'audit/v2/BOUNDED_COMPATIBILITY.md'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, GUIDE,
         ROOT / 'audit/v2/compatibility_analysis.py']


def prepare():
    config = replay.read_json(CONFIG)
    root = (ROOT / config['parent_run']).resolve()
    parent = replay.read_json(root / 'run.json')
    if parent.get('status') != 'complete' or parent.get('source_inputs_unchanged') is not True:
        raise ValueError('Expected the completed unchanged bounded-window evidence')
    hashes = previous.parent.verify_hashes(root, parent)
    profile = parent['profile']
    if profile['case'] != config['case']:
        raise ValueError('Parent case differs from fixed audit design')
    cells = parent['cells']
    ids = [c['source']['id'] for c in cells]
    ir_cells = [c for c in cells if c['source']['route'] == 'serviceflow_ir']
    if (len(cells) != config['expected_original_cells'] or len(ir_cells) != config['expected_ir_cells']
            or len(set(ids)) != len(ids) or any(c['source']['case'] != config['case'] for c in cells)
            or set(parent['models']) != {c['source']['id'] for c in ir_cells}):
        raise ValueError('Incomplete, duplicated, or changed immutable case roster')
    # Resolve the same frozen public workspace used by the parent, without
    # selecting by success or reading private assertion/native runtime files.
    inventory = replay.read_json(ROOT / replay.read_json(previous.parent.CONFIG)['inventory_run'] / 'run.json')
    workspace = Path(inventory['control_directory']) / 'cases' / config['case'] / 'public_workspace' / config['case']
    active = workspace / 'fixtures/scenarios/nominal'
    schema_path = ROOT / 'schemas/serviceflow_ir.schema.json'
    schema = replay.read_json(schema_path)
    if any(isinstance(v, dict) and any(k in v and not str(v[k]).startswith('#') for k in ('$ref', '$dynamicRef'))
           for v in previous.planner.analysis.walk(schema)):
        raise ValueError('IR schema has nonlocal references; do not fetch schemas')
    analysis.Draft202012Validator.check_schema(schema)
    files = [*FILES, root / 'run.json', root / 'input_sha256.json', schema_path]
    hashes.update({str(p.resolve()): controls.sha256(p) for p in files})
    return config, parent, cells, workspace, active, schema, hashes


def inspect_cell(cell, parent, workspace, active, schema, config, catalog):
    source = cell['source']; path = Path(source['artifact'])
    record = {'source': source, 'prior_replay_state': parent['models'][source['id']]['state'],
              'artifact_sha256': controls.sha256(path) if path.is_file() else 'MISSING'}
    if not path.is_file():
        record['analysis'] = {'state': 'missing_saved_ir', 'findings': [], 'semantic_outcome': 'not_measured', 'execution_ready': False}
        return record
    if path.stat().st_size > config['max_document_bytes']:
        record['analysis'] = {'state': 'inspection_limit', 'findings': [], 'semantic_outcome': 'not_measured', 'execution_ready': False}
        return record
    try:
        ir = controls.load(path)
    except (ValueError, TypeError, OSError, controls.yaml.YAMLError) as exc:
        record['analysis'] = {'state': 'parse_error', 'error_type': type(exc).__name__, 'findings': [],
                              'semantic_outcome': 'not_measured', 'execution_ready': False}
        return record
    record['analysis'] = analysis.analyze(
        ir, schema=schema, catalog_get=lambda service, version: catalog.get(workspace, service, version),
        active=active, operations={s: pair[0] for s, pair in previous.engine.OPERATIONS.items()},
        fixture_keys=list(parent['profile']['input_keys'].values()), load_json=replay.read_json,
        max_bytes=config['max_document_bytes'])
    return record


def summarize(records):
    counts, cell_counts, codes = Counter(), Counter(), Counter()
    for record in records:
        categories = set()
        for finding in record['analysis']['findings']:
            category = finding['category']; categories.add(category)
            counts[category] += 1; codes[(category, finding['code'])] += 1
        cell_counts.update(categories)
    return {'states': dict(Counter(r['analysis']['state'] for r in records)),
            'cells_by_category': dict(cell_counts), 'findings_by_category': dict(counts),
            'finding_codes': [{'category': cat, 'code': code, 'count': n} for (cat, code), n in sorted(codes.items())]}


def render(run, records):
    counts = run['counts']
    lines = ['# Bounded-window static compatibility audit', '',
        f"Protocol {run['audit_protocol_version']}; status {run['status']}; original cells {len(run['cells'])}; IR records {len(records)}.",
        'Zero LLM calls, workflow executions, and repairs. No original gate or semantic scores are measured.', '',
        'Findings collect independent checks, including later blockers hidden by the old first rejection.',
        'Categories overlap; their cell counts must not be added together.', '',
        '| Finding category | Cells affected | Findings |', '|---|---:|---:|']
    for category in analysis.CATEGORIES:
        lines.append(f"| {category} | {counts['cells_by_category'].get(category, 0)} | {counts['findings_by_category'].get(category, 0)} |")
    lines += ['', '## Inspection states', '']
    lines += [f'- {state}: {n}' for state, n in sorted(counts['states'].items())]
    lines += ['', '## Every saved IR cell', '',
              '| Model | Method | Sample | State | Catalog | Structure/dataflow | v2 input | Adapter | Unspecified |',
              '|---|---|---:|---|---:|---:|---:|---:|---:|']
    for record in records:
        s, a = record['source'], record['analysis']; c = a.get('finding_counts', {})
        lines.append(f"| {s['model']} | {s['method']} | {s['sample_index']} | {a['state']} | {c.get('public_catalog',0)} | {c.get('saved_structure',0)+c.get('dataflow',0)} | {c.get('v2_input_mapping',0)} | {c.get('adapter_limit',0)} | {c.get('public_semantics_unspecified',0)} |")
    lines += ['', '## Interpretation', '',
        '- `public_catalog`: a violation of an explicit checked service declaration; not the complete public-gate validator.',
        '- `saved_structure` / `dataflow`: schema, identity, writer, or dependency problems.',
        '- `v2_input_mapping`: missing/unusable explicit input links under the new mapping convention; not automatically an old contract violation.',
        '- `adapter_limit`: a requirement narrower than the catalog or an unimplemented case.',
        '- `public_semantics_unspecified`: the catalog does not enumerate profile values; a different string alone does not prove semantic error.',
        '- Missing saved IR remains an availability outcome; no executed failures or passes are inferred.',
        '- An absence of findings is not execution readiness or a semantic pass. Direct-Argo cells remain a separate unexecuted route.', '',
        'Use findings.json for all located findings and file links. Freeze any future compatibility or repair rules before another replay.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Verify parent evidence and roster; do not inspect cells or write outputs')
    args = parser.parse_args(argv)
    print('Verifying unchanged parent inputs and the fixed 54-cell roster...', flush=True)
    config, parent, cells, workspace, active, schema, hashes = prepare()
    if args.dry_run:
        print(json.dumps({'case': config['case'], 'original_cells': len(cells), 'ir_cells': config['expected_ir_cells'],
                          'llm_calls': 0, 'workflow_executions': 0, 'repairs': 0}, indent=2)); return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'audit/outputs' / f'package_v2_bounded_compatibility__{stamp}__{uuid.uuid4().hex[:8]}'
    output.mkdir(parents=True, exist_ok=False)
    for path in FILES:
        target = output / 'implementation' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    run = {'audit_protocol_version': config['audit_protocol_version'], 'package_version': config['package_version'],
           'status': 'running', 'design': config, 'cells': cells, 'environment': controls.environment(),
           'input_fingerprint': controls.fingerprint(hashes), 'llm_calls': 0, 'workflow_executions': 0, 'repairs': 0}
    controls.write_json(output / 'input_sha256.json', hashes); controls.write_json(output / 'run.json', run)
    print(f'Output: {output}', flush=True)
    verification = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT,
                                  capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(verification.stdout + verification.stderr)
    if verification.returncode:
        run['status'] = 'verification_failed'; controls.write_json(output / 'run.json', run)
        print(f'verification_failed: {output / "verification.txt"}', flush=True); return 1
    catalog = previous.planner.analysis.Catalog(controls.load)
    records = []
    for cell in cells:
        if cell['source']['route'] != 'serviceflow_ir':
            continue
        try:
            record = inspect_cell(cell, parent, workspace, active, schema, config, catalog)
        except Exception as exc:
            record = {'source': cell['source'], 'analysis': {'state': 'inspection_error', 'findings': [],
                      'error_type': type(exc).__name__, 'execution_ready': False, 'semantic_outcome': 'not_measured'}}
        records.append(record)
        controls.write_json(output / 'findings.json', records)
        print(cell['source']['id'] + ': ' + record['analysis']['state'], flush=True)
    counts = summarize(records); run['counts'] = counts
    controls.write_json(output / 'counts.json', counts)
    stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=['cell', 'category', 'code', 'subject'])
    writer.writeheader()
    for record in records:
        for finding in record['analysis']['findings']:
            writer.writerow({'cell': record['source']['id'], **{k: finding[k] for k in ('category', 'code', 'subject')}})
    (output / 'findings.csv').write_text(stream.getvalue())
    try:
        previous.parent.verify_hashes(output, run)
        unchanged = True
    except ValueError:
        unchanged = False
    run['source_inputs_unchanged'] = unchanged
    errors = (len(records) != config['expected_ir_cells'] or any(r['analysis']['state'] in ('inspection_error', 'inspection_limit')
              or r['analysis'].get('finding_counts', {}).get('inspection_error', 0) for r in records))
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if errors else 'complete'
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run, records))
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
