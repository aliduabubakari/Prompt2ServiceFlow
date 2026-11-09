#!/usr/bin/env python3
"""Gated paired v2 compatibility/binding-repair replay; zero model calls."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
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
import audit_v2_bounded_compatibility as compatibility
import paired_window_executor as engine
import paired_window_repair as repairer
import paired_window_oracle as oracle

base = compatibility.previous
controls, replay = base.controls, base.replay
CONFIG = ROOT / 'audit/v2/paired_window_study.json'
TESTS = ROOT / 'tests/unit/test_v2_paired_window.py'
FILES = [Path(__file__).resolve(), CONFIG, TESTS, ROOT / 'audit/v2/PAIRED_WINDOW_STUDY.md',
         ROOT / 'audit/v2/paired_window_executor.py', ROOT / 'audit/v2/paired_window_repair.py', ROOT / 'audit/v2/paired_window_oracle.py']


def prepare():
    config = replay.read_json(CONFIG)
    if (config['conditions'] != ['compatibility', 'binding_repair'] or config['repairs'] != ['unique_public_manifest', 'required_status']
            or config['profile_dispatch'] != 'external_v2_profile_overrides_all_original_string_labels'):
        raise ValueError('Study rules changed; implementation/version review required')
    _, bounded, cells, workspace, active, schema, hashes = compatibility.prepare()
    root = ROOT / config['parent_compatibility']; prior = replay.read_json(root / 'run.json')
    if prior['status'] != 'complete' or prior.get('source_inputs_unchanged') is not True or prior['cells'] != cells:
        raise ValueError('Expected the completed immutable compatibility cohort')
    hashes.update(base.parent.verify_hashes(root, prior))
    if (config['case'] != bounded['profile']['case'] or len(cells) != config['expected_original_cells']
            or sum(c['source']['route'] == 'serviceflow_ir' for c in cells) != config['expected_ir_cells']):
        raise ValueError('Study case/roster changed')
    fixtures = Path(bounded['scenario_inputs'])
    actual = {p.relative_to(fixtures).as_posix(): controls.sha256(p) for p in fixtures.rglob('*') if p.is_file()}
    if actual != bounded['scenario_input_sha256']:
        raise ValueError('Original derived scenarios changed')
    hashes.update({str((fixtures / name).resolve()): digest for name, digest in actual.items()})
    hashes.update({str(p.resolve()): controls.sha256(p) for p in [*FILES, root / 'run.json', root / 'input_sha256.json', root / 'findings.json']})
    profile = {**bounded['profile'], 'package_version': config['package_version'], 'audit_protocol_version': config['audit_protocol_version'],
               'interpretation': config['interpretation'], 'profile_dispatch': config['profile_dispatch']}
    return config, cells, workspace, active, fixtures, schema, hashes, profile


def diagnose(ir, workspace, active, schema, catalog, profile):
    return compatibility.analysis.analyze(ir, schema=schema,
        catalog_get=lambda service, version: catalog.get(workspace, service, version), active=active,
        operations={s: p[0] for s, p in engine.OPERATIONS.items()}, fixture_keys=list(profile['input_keys'].values()),
        load_json=replay.read_json)


def hard_findings(diagnostic, allow_missing_status=False):
    return [f for f in diagnostic['findings'] if f['category'] in ('saved_structure', 'public_catalog', 'dataflow', 'inspection_error')
            and not (allow_missing_status and f['category'] == 'public_catalog' and f['code'] == 'required_service_port_unbound'
                     and f['subject'].endswith('/output_bindings/execution_report'))]


def effective(ir, condition, workspace, active, schema, catalog, profile):
    if condition not in ('compatibility', 'binding_repair'):
        raise ValueError('Unknown condition')
    initial = diagnose(ir, workspace, active, schema, catalog, profile)
    metadata = {'initial_diagnostics': initial, 'edits': [], 'repair_decisions': []}
    if initial.get('state') != 'inspected' or hard_findings(initial, condition == 'binding_repair'):
        metadata['state'] = 'inspection_error' if any(f['category'] == 'inspection_error' for f in initial['findings']) else 'invalid_checked_contracts'
        return copy.deepcopy(ir), metadata
    value = copy.deepcopy(ir)
    if condition == 'binding_repair':
        value, metadata['edits'], metadata['repair_decisions'] = repairer.repair(
            ir, profile, active, lambda service, version: catalog.get(workspace, service, version))
    final = diagnose(value, workspace, active, schema, catalog, profile)
    metadata['effective_diagnostics'] = final
    if hard_findings(final):
        metadata['state'] = 'inspection_error' if any(f['category'] == 'inspection_error' for f in final['findings']) else 'invalid_checked_contracts'
    elif any(f['category'] == 'v2_input_mapping' for f in final['findings']):
        metadata['state'] = 'unsupported_input_mapping'
    else:
        try:
            metadata['plan'] = engine.compile_plan(value)
            metadata['state'] = 'ready_for_v2_scenarios'
        except base.ops.Unsupported as exc:
            metadata.update(state='unsupported_execution_contract', reason=str(exc))
        except (ValueError, KeyError, TypeError) as exc:
            metadata.update(state='invalid_execution_contract', reason=f'{type(exc).__name__}: {exc}')
    return value, metadata


def install(ir, profile, root, fixtures):
    manifest = base.install(ir, profile, root, fixtures, profile['scenarios'])
    scripts = root / 'runtime/scripts'
    for filename in ('paired_window_executor.py', 'bounded_window_executor.py'):
        shutil.copy2(ROOT / 'audit/v2' / filename, scripts / filename)
    (scripts / 'workflow.py').write_text(
        'import argparse,json\nfrom pathlib import Path\nfrom paired_window_executor import execute\n'
        'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path)\n'
        'a=p.parse_args();root=Path(__file__).parent\n'
        'r=execute(json.loads((root/"ir.json").read_text()),json.loads((root/"profile.json").read_text()),a.workspace,a.fixtures)\n'
        'print(json.dumps(r));raise SystemExit(0 if r["workflow_status"]=="completed" else 2)\n')
    return manifest


def run_condition(ir, condition, profile, workspace, active, fixtures, schema, catalog, attempt, source_path=None):
    attempt.mkdir(parents=True, exist_ok=False)
    if source_path:
        shutil.copy2(source_path, attempt / 'original_ir.yaml')
    else:
        (attempt / 'original_ir.yaml').write_text(controls.yaml.safe_dump(ir, sort_keys=False))
    original_digest = controls.sha256(attempt / 'original_ir.yaml')
    value, record = effective(ir, condition, workspace, active, schema, catalog, profile)
    controls.write_json(attempt / 'diagnostics.json', record)
    controls.write_json(attempt / 'edits.json', record['edits'])
    if record['edits']:
        (attempt / 'effective_ir.yaml').write_text(controls.yaml.safe_dump(value, sort_keys=False))
    else:
        shutil.copy2(attempt / 'original_ir.yaml', attempt / 'effective_ir.yaml')
    record.update(condition=condition, artifact_directory=str(attempt), source_ir_sha256=original_digest,
                  effective_ir_sha256=controls.sha256(attempt / 'effective_ir.yaml'), original_public_gates='not_measured', original_g6_assert='not_measured')
    if condition == 'compatibility' and (record['edits'] or record['source_ir_sha256'] != record['effective_ir_sha256']):
        raise ValueError('Compatibility condition must preserve exact original IR bytes')
    if record['state'] != 'ready_for_v2_scenarios':
        return record, [], value
    try:
        schemas = base.schemas_for(value, workspace)
        manifest = install(value, profile, attempt / 'instance', fixtures)
        raw = controls._execute_scenarios(attempt / 'instance', manifest, sandbox_generated=True)
        record['execution'] = controls.persist_snapshots(raw, attempt / 'execution')
        record['scenarios'] = {r['scenario']: oracle.check(r, value, fixtures / 'scenarios' / r['scenario'], profile, r['scenario'], schemas) for r in raw}
        record['profile_all_scenarios_pass'] = (set(record['scenarios']) == set(profile['scenarios'])
                                               and all(v['pass'] for v in record['scenarios'].values()))
        record['state'] = 'evaluated_under_v2'
    except base.ops.Unsupported as exc:
        record.update(state='unsupported_public_schema', reason=str(exc)); raw = []
    controls.write_json(attempt / 'result.json', record)
    return record, raw, value


def negative_controls(nominal, ir, profile, fixtures, directory):
    # The four prior numeric/publication mutations remain meaningful. Order
    # only the evaluator view by explicit role; never change the executed IR.
    view = copy.deepcopy(ir); primary = oracle.primary(ir)
    publisher = next(b for b in view['bindings'] if b['service_id'] == oracle.base.PUBLISHER)
    publisher['output_bindings'].sort(key=lambda o: o['artifact_id'] != primary)
    results = base.negative_controls(nominal, view, fixtures, profile, directory)
    original_publisher = next(b for b in ir['bindings'] if b['service_id'] == oracle.base.PUBLISHER)
    mutations = [('wrong_bound_status', next(o['artifact_id'] for o in original_publisher['output_bindings'] if o['port'] == 'execution_report'))]
    mutations += [('wrong_bound_audit', o['artifact_id']) for o in original_publisher['output_bindings']
                  if o['port'] == 'output_artifacts' and o['artifact_id'] != primary]
    for name, identity in mutations:
        mutant = copy.deepcopy(nominal); path = 'artifacts/' + identity + '.json'
        value = json.loads(mutant['_snapshot'][path])
        if name == 'wrong_bound_status':
            value['success'] = False
        else:
            value['counts'] = {**value['counts'], 'raw_rows': value['counts']['raw_rows'] + 1}
        mutant['_snapshot'][path] = json.dumps(value).encode()
        controls.persist_snapshots([mutant], directory / name)
        check = oracle.check(mutant, ir, fixtures, profile, 'nominal')
        results[name] = {'detected': not check['pass'], 'evaluation': check}
    return results


def reference_variants(ir):
    split = copy.deepcopy(ir)
    publisher = next(b for b in split['bindings'] if b['service_id'] == oracle.base.PUBLISHER)
    identities = {a['artifact_id'] for a in split['artifacts']}; identity = publisher['intent_id'] + '_v2_bound_audit'
    if identity in identities:
        raise ValueError('Reference control audit ID collision')
    split['artifacts'].append({'artifact_id': identity, 'name': 'Bound publication audit', 'kind': 'artifact',
        'data_type': 'json', 'media_type': 'application/json', 'role': 'report', 'producer': publisher['intent_id'],
        'consumers': [], 'sensitivity': 'internal', 'persistence': 'workflow'})
    publisher['output_bindings'].append({'port': 'output_artifacts', 'artifact_id': identity})
    damaged = copy.deepcopy(split)
    statuses = {o['artifact_id'] for b in damaged['bindings'] for o in b['output_bindings'] if o['port'] == 'execution_report'}
    if any(i['artifact_id'] in statuses for b in damaged['bindings'] for i in b['input_bindings']):
        raise ValueError('Cannot remove a consumed reference status for this control')
    for b in damaged['bindings']:
        b['output_bindings'] = [o for o in b['output_bindings'] if o['artifact_id'] not in statuses]
    damaged['artifacts'] = [a for a in damaged['artifacts'] if a['artifact_id'] not in statuses]
    ingestor = next(b for b in damaged['bindings'] if b['service_id'] == repairer.INGESTOR)
    external = next(a for a in damaged['artifacts'] if a['artifact_id'] == ingestor['input_bindings'][0]['artifact_id'])
    del external['fixture_ref']
    return [('original_reference', 'compatibility', ir), ('publication_roles', 'compatibility', split),
            ('missing_bindings_control', 'binding_repair', damaged)]


def control_pass(record, name):
    expected = {'constant_summary', 'wrong_energy', 'wrong_alert', 'missing_publication', 'wrong_bound_status'}
    if name != 'original_reference':
        expected.add('wrong_bound_audit')
    return (record.get('profile_all_scenarios_pass') is True
            and set(record.get('negative_controls', {})) == expected
            and all(n['detected'] for n in record['negative_controls'].values())
            and (name != 'missing_bindings_control' or Counter(e['rule'] for e in record['edits']) == {'unique_public_manifest': 1, 'required_status': 12}))


def failure_record(attempt, exc, state):
    # Preserve already planned/logged edits even if infrastructure fails later.
    path = attempt / 'diagnostics.json'
    record = replay.read_json(path) if path.is_file() else {'edits': []}
    record.update(state=state, reason=f'{type(exc).__name__}: {exc}', artifact_directory=str(attempt))
    return record


def render(run):
    lines = ['# Paired v2 compatibility and binding-repair replay', '',
        f"Package {run['package_version']}; protocol {run['audit_protocol_version']}; status {run['status']}; LLM calls 0.",
        'New external runtime interpretation; no replacement of original method outcomes or G6-Assert scores.', '',
        f"Original ledger: {len(run['cells'])} cells; 27 direct-Argo cells unexecuted; 27 IR cells × two conditions.", '',
        '## Reference/control gate', '', '| Control | Scenario checks | Negative controls detected | Gate |', '|---|---:|---:|---|']
    for name, record in run.get('controls', {}).items():
        lines.append(f"| {name} | {sum(v['pass'] for v in record.get('scenarios', {}).values())}/9 | {sum(v['detected'] for v in record.get('negative_controls', {}).values())}/{5 if name=='original_reference' else 6} | {control_pass(record,name)} |")
    lines += ['', '## Paired saved-output results', '',
        '| Model | Method | Sample | Original status | Compatibility | Checks | Binding repair | Checks | IR edits |',
        '|---|---|---:|---|---|---:|---|---:|---:|']
    def count(record):
        return str(sum(s['pass'] for s in record['scenarios'].values())) + '/9' if 'scenarios' in record else 'not executed'
    for cell in run['cells']:
        source = cell['source']
        if source['route'] != 'serviceflow_ir':
            continue
        pair = run.get('results', {}).get(source['id'], {})
        a, b = pair.get('compatibility', {'state': 'pending'}), pair.get('binding_repair', {'state': 'pending'})
        lines.append(f"| {source['model']} | {source['method']} | {source['sample_index']} | {source.get('original_method_status')} | {a['state']} | {count(a)} | {b['state']} | {count(b)} | {len(b.get('edits',[]))} |")
    lines += ['', 'Scenario checks include six positive cases and three expected input rejections; they are not nine successful executions.',
        'Unexecuted cells are not labeled 0/9 semantic failures. Original budget-exhausted statuses remain unchanged.',
        'Eligibility, edits, override/projection plans, schemas, actual outputs, and paired outcomes remain in run.json and attempt directories.',
        'No missing submission, unknown service, ambiguous writer, or existing wrong fixture reference is reconstructed.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true'); parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    print('Verifying the fixed cohort, prior evidence, code, and derived public scenarios...', flush=True)
    config, cells, workspace, active, fixtures, schema, hashes, profile = prepare()
    if args.dry_run:
        print(json.dumps({'case': config['case'], 'original_cells': len(cells), 'ir_cells': 27, 'conditions': config['conditions'],
            'model_condition_records': 54, 'reference_control_scenarios': 27, 'negative_controls': 17,
            'maximum_model_scenarios': 486, 'llm_calls': 0, 'published_scores_replaced': False}, indent=2)); return 0
    if args.resume:
        output = args.resume.resolve(); run = replay.read_json(output / 'run.json')
        if run['input_fingerprint'] != controls.fingerprint(hashes) or run['cells'] != cells or run['profile'] != profile:
            raise ValueError('Study inputs/rules/code changed; cannot resume this condition')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_paired_window__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': config['package_version'], 'audit_protocol_version': config['audit_protocol_version'],
            'design': config, 'profile': profile, 'cells': cells, 'input_fingerprint': controls.fingerprint(hashes),
            'environment': controls.environment(), 'llm_calls': 0, 'controls': {}, 'results': {}}
        controls.write_json(output / 'input_sha256.json', hashes)
        for path in FILES:
            target = output / 'implementation' / path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    run['status'] = 'running'; controls.write_json(output / 'run.json', run)
    print(f'Output: {output}', flush=True)
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode:
        run['status'] = 'verification_failed'; controls.write_json(output / 'run.json', run)
        print(f'verification_failed: {output / "verification.txt"}', flush=True); return 1
    catalog = base.planner.analysis.Catalog(controls.load)
    reference = controls.load(controls.BENCHMARK / 'instances' / config['case'] / 'gold/serviceflow.yaml')
    for name, condition, ir in reference_variants(reference):
        if name in run['controls']:
            continue
        attempt = output / 'controls' / name / ('attempt_' + uuid.uuid4().hex[:8])
        try:
            record, raw, value = run_condition(ir, condition, profile, workspace, active, fixtures, schema, catalog, attempt)
            if record.get('profile_all_scenarios_pass'):
                record['negative_controls'] = negative_controls(next(r for r in raw if r['scenario'] == 'nominal'), value, profile,
                    fixtures / 'scenarios/nominal', attempt / 'negative_controls')
        except Exception as exc:
            record = failure_record(attempt, exc, 'control_error')
        run['controls'][name] = record; controls.write_json(output / 'run.json', run)
        print(f'Control {name}: gate={control_pass(record,name)}', flush=True)
    if len(run['controls']) != 3 or not all(control_pass(r,n) for n,r in run['controls'].items()):
        run['status'] = 'reference_controls_failed'; controls.write_json(output / 'run.json', run)
        (output / 'summary.md').write_text(render(run)); print(f"reference_controls_failed: {output / 'summary.md'}", flush=True); return 1
    for cell in cells:
        source = cell['source']
        if source['route'] != 'serviceflow_ir':
            continue
        pair = run['results'].setdefault(source['id'], {})
        for condition in config['conditions']:
            if condition in pair:
                continue
            attempt = output / 'models' / ('attempt_' + uuid.uuid4().hex[:8]); path = Path(source['artifact'])
            try:
                if not path.is_file():
                    record = {'state': 'missing_saved_ir', 'edits': []}
                elif path.stat().st_size > config['max_document_bytes']:
                    record = {'state': 'inspection_limit', 'edits': []}
                else:
                    try:
                        ir = controls.load(path)
                    except (ValueError, TypeError, controls.yaml.YAMLError) as exc:
                        record = {'state': 'invalid_saved_ir', 'edits': [], 'error_type': type(exc).__name__}
                    else:
                        record, _, _ = run_condition(ir, condition, profile, workspace, active, fixtures, schema, catalog, attempt, path)
            except Exception as exc:
                record = failure_record(attempt, exc, 'runner_error')
            record['artifact_directory'] = str(attempt); controls.write_json(attempt / 'result.json', record)
            pair[condition] = record; controls.write_json(output / 'run.json', run)
            (output / 'summary.md').write_text(render(run))
            print(source['id'] + ' ' + condition + ': ' + record['state'], flush=True)
    try:
        base.parent.verify_hashes(output, run); unchanged = True
    except ValueError as exc:
        unchanged = False; run['integrity_error'] = str(exc)
    complete = (len(run['results']) == config['expected_ir_cells'] and all(set(p) == set(config['conditions']) for p in run['results'].values()))
    errors = any(r['state'] in ('runner_error', 'inspection_error', 'inspection_limit') for pair in run['results'].values() for r in pair.values())
    run['source_inputs_unchanged'] = unchanged
    run['status'] = 'inputs_changed' if not unchanged else 'complete_with_errors' if errors or not complete else 'complete'
    controls.write_json(output / 'paired_results.json', run['results']); controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=['cell','condition','state','original_method_status','edits','scenario_checks_passed','scenario_checks_observed'])
    writer.writeheader()
    for cell in cells:
        for condition, record in run['results'].get(cell['source']['id'], {}).items():
            scenarios = record.get('scenarios', {})
            writer.writerow({'cell': cell['source']['id'], 'condition': condition, 'state': record['state'],
                'original_method_status': cell['source'].get('original_method_status'), 'edits': len(record.get('edits',[])),
                'scenario_checks_passed': sum(s['pass'] for s in scenarios.values()) if scenarios else '', 'scenario_checks_observed': len(scenarios)})
    (output / 'paired_results.csv').write_text(stream.getvalue())
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
