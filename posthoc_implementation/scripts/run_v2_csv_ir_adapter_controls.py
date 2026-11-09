#!/usr/bin/env python3
"""Verify authored IR projection controls before any saved-model replay."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'audit/v2')); sys.path.insert(0, str(ROOT / 'audit'))
import audit_v2_csv_replay_eligibility as prior
import csv_ir_adapter as adapter
import csv_ir_adapter_controls as factory

controls, replay = prior.controls, prior.replay
ops, oracle, transport = prior.previous.ops, prior.previous.oracle, prior.previous.transport
CONFIG = ROOT / 'audit/v2/csv_ir_adapter_controls.v1.json'
TEST = ROOT / 'tests/unit/test_v2_csv_ir_adapter.py'
DOC = ROOT / 'audit/v2/CSV_IR_ADAPTER_CONTROLS.md'


def prepare():
    config = replay.read_json(CONFIG)
    if config['adapter_version'] != adapter.VERSION: raise ValueError('Adapter version differs')
    parent = ROOT / config['eligibility_run']; run = replay.read_json(parent / 'run.json')
    if run['status'] != 'complete' or run.get('source_inputs_unchanged') is not True: raise ValueError('Completed unchanged eligibility audit required')
    hashes = prior.previous.coverage.frozen.parent.verify_hashes(parent, run)
    prior.verify_roster(run['sources'], run['design'])
    if len(run['completed_cells']) != config['expected_cells_in_prior_audit']: raise ValueError('Eligibility coverage differs')
    paths = [CONFIG, TEST, DOC, Path(__file__).resolve(), Path(adapter.__file__), Path(factory.__file__), parent / 'run.json', parent / 'input_sha256.json']
    ids = {s['id'] for s in run['sources']}
    if set(run['completed_cells']) != ids: raise ValueError('Checkpoint identities differ')
    for name, saved in run['completed_cells'].items():
        path = Path(saved['path'])
        if controls.sha256(path) != saved['sha256'] or replay.read_json(path)['source']['id'] != name: raise ValueError('Eligibility checkpoint changed')
        paths.append(path)
    baseline = ROOT / config['public_baseline']
    contract_root = baseline / config['output_contract_case'] / 'public_workspace' / config['output_contract_case']
    schemas = {}
    for filename in set(factory.SCHEMA_NAMES.values()):
        ref = 'contracts/artifacts/' + filename; path = contract_root / ref
        schemas[ref] = replay.read_json(path); adapter.checked_schema(schemas[ref]); paths.append(path)
    cases = []
    for spec in config['cases']:
        workspace = baseline / spec['case'] / 'public_workspace' / spec['case']
        path = ops.inside(workspace, spec['source_csv']); raw = path.read_bytes()
        oracle.expected_csv(raw)
        cases.append({**spec, 'raw': raw, 'source': str(path)}); paths.append(path)
        descriptor = workspace / 'catalog/services' / (spec['loader_service'] + '.yaml')
        paths.append(descriptor)
    for path in paths:
        key = str(path.resolve()); value = controls.sha256(path)
        if key in hashes and hashes[key] != value: raise ValueError('Prior pin changed: ' + key)
        hashes[key] = value
    return {'config': config, 'hashes': hashes, 'schemas': schemas, 'cases': cases}


def reset(database):
    for schema in ('p2sf_adapter', 'p2sf_other'):
        database.sql('DROP SCHEMA IF EXISTS ' + ops.ident(schema) + ' CASCADE; CREATE SCHEMA ' + ops.ident(schema))


def target(ir):
    binding = next(b for b in ir['bindings'] if b['service_id'] in (adapter.SNAPSHOT, adapter.TABULAR))
    p = binding['parameter_bindings']
    label = p['import_spec']['target_table'] if binding['service_id'] == adapter.SNAPSHOT else p['target_table']
    return adapter.target_name(label, 'p2sf_adapter')


def parameters(ir, service): return next(b['parameter_bindings'] for b in ir['bindings'] if b['service_id'] == service)


def save_dump(database, directory):
    (directory / 'target.sql').write_text(transport.docker('exec', database.name, 'pg_dump', '-U', 'postgres', '-d', 'p2sf_controls',
        '--schema=p2sf_adapter', '--schema=p2sf_other', '--no-owner', '--no-privileges'))


def trial(database, case, scenario, directory, schemas, config):
    directory.mkdir(parents=True, exist_ok=False); reset(database)
    raw = case['raw']; header, rows = oracle.expected_csv(raw)
    if scenario == 'renamed_columns': raw = factory.encode_csv([['column_' + str(i) for i in range(len(header))], *rows])
    elif scenario == 'changed_values':
        rows[0][-1] = 'a changed business value'; raw = factory.encode_csv([header, *rows])
    elif scenario == 'quoted_multiline':
        rows[0][-1] = 'Unicode Δ, "quoted"\nline; SELECT \'literal\''; raw = factory.encode_csv([header, *rows])
    ir, intervention = factory.authored(raw, case['loader_service'], directory / 'fixtures', missing=scenario == 'missing_file',
        logical_output='/reports/validated.json' if scenario == 'absolute_output' else 'reports/validated.json',
        mode='append' if scenario == 'repeat_append' else 'replace')
    schema_set = copy.deepcopy(schemas); p = parameters(ir, case['loader_service']); expect = None
    if scenario == 'renamed_ids': ir = factory.renamed(ir)
    elif scenario == 'other_schema':
        if case['loader_service'] == adapter.SNAPSHOT: p['import_spec']['target_table'] = 'p2sf_other.records_generic'
        else: p['target_table'] = 'p2sf_other.records_generic'
    elif scenario == 'nonmatching_glob': parameters(ir, adapter.SENSOR)['filename_pattern'] = 'absent_*.csv'
    elif scenario == 'missing_binding':
        next(a for a in ir['artifacts'] if a['artifact_id'] == 'origin').pop('fixture_ref'); expect = 'missing_fixture_link'
    elif scenario == 'upsert_without_keys':
        p['load_mode' if case['loader_service'] == adapter.SNAPSHOT else 'write_mode'] = 'upsert'; expect = 'unsupported_write_mode'
    elif scenario == 'missing_columns': parameters(ir, adapter.CSV).pop('required_columns'); expect = 'missing_required_columns'
    elif scenario == 'nonidentity_columns':
        if case['loader_service'] == adapter.SNAPSHOT:
            p['import_spec']['columns'] = list(reversed(header)); expect = 'nonidentity_columns'
        else:
            p['column_mapping'] = {'x': 'y'}; expect = 'unsupported_loader'
    elif scenario == 'template': parameters(ir, adapter.CSV)['output_path'] = '/data/{{ ds }}/file.json'; expect = 'unresolved_parameters'
    elif scenario == 'wrong_port_type': ir['artifacts'][0]['data_type'] = 'object'; expect = 'port_type_mismatch'
    elif scenario == 'missing_dependency': ir['control_flow']['edges'].pop(); expect = 'unsupported_dependency'
    elif scenario == 'wrong_gate': ir['control_flow']['gates'][0]['condition'] = 'true'; expect = 'unsupported_gate'
    elif scenario == 'output_schema':
        schema_set['contracts/artifacts/availability_decision.schema.json']['properties']['available']['type'] = 'integer'
        expect = 'output_schema_mismatch'
    elif scenario == 'fixture_tamper':
        (directory / 'fixtures/payload.csv').write_bytes(raw + b'tampered'); expect = 'fixture_hash_mismatch'
    schema, table = target(ir)
    if scenario == 'transactional_rollback':
        initial = adapter.compile_projection(ir, intervention, schema_set)
        adapter.execute(initial, database, directory / 'fixtures', directory / 'initial')
        database.sql('ALTER TABLE ' + ops.ident(schema) + '.' + ops.ident(table) + ' ADD CONSTRAINT rejected CHECK (' + ops.ident(header[0]) + " <> '__reject_control__')")
        rows[-1][0] = '__reject_control__'; raw = factory.encode_csv([header, *rows])
        path = directory / 'fixtures/payload.csv'; path.write_bytes(raw)
        intervention['fixtures']['control/source']['sha256'] = controls.sha256(path)
    controls.write_json(directory / 'source_projection.json', ir); controls.write_json(directory / 'intervention.json', intervention)
    controls.write_json(directory / 'schemas.json', schema_set)
    before = oracle.observe(database, schema, table); result = None; failure = None
    try:
        plan = adapter.compile_projection(ir, intervention, schema_set); controls.write_json(directory / 'plan.json', plan)
        result = adapter.execute(plan, database, directory / 'fixtures', directory / 'execution')
        if scenario in ('repeat_append', 'repeat_replace'):
            if scenario == 'repeat_replace':
                h, r = oracle.expected_csv(raw); r[-1][-1] = 'replacement'; raw = factory.encode_csv([h, *r])
                f = directory / 'fixtures/payload.csv'; f.write_bytes(raw)
                intervention['fixtures']['control/source']['sha256'] = controls.sha256(f)
                plan = adapter.compile_projection(ir, intervention, schema_set)
            controls.write_json(directory / 'repeat_plan.json', plan)
            result = adapter.execute(plan, database, directory / 'fixtures', directory / 'repeat')
    except ops.ContractError as exc: failure = {'code': exc.code, 'message': str(exc)}
    except transport.DatabaseError as exc: failure = {'sqlstate': exc.sqlstate, 'message': str(exc)}
    after = oracle.observe(database, schema, table)
    if scenario in config['positives']:
        checked = oracle.check_loaded(after, raw, (result or {}).get('load_status') or {}, repetitions=2 if scenario == 'repeat_append' else 1)
        checks = checked['checks']; checks['no_refusal'] = failure is None
        checks['unchanged_projection'] = ir == replay.read_json(directory / 'source_projection.json') and bool((result or {}).get('source_ir_unchanged'))
        checks['count_contract'] = ((result or {}).get('load_status') or {}).get('rows_loaded') == len(oracle.expected_csv(raw)[1])
        output = next((r for r in (result or {}).get('outputs', {}).values() if 'materialized_alias' in r), None)
        base = directory / ('repeat' if scenario.startswith('repeat_') else 'execution')
        checks['logical_alias_equals_bound_dataset'] = bool(output and (base / output['path']).read_bytes() == (base / output['materialized_alias']).read_bytes())
    elif scenario in config['gates']:
        checks = {'missing_input_gate': (result or {}).get('state') == 'skipped_missing_input',
            'loader_not_called': (result or {}).get('loader_called') is False,
            'dependent_loader_skipped': (result or {}).get('events', [{}])[-1].get('state') == 'skipped_dependency_or_gate',
            'database_unchanged': oracle.same_state(before, after), 'no_refusal': failure is None}
    else:
        checks = {'expected_refusal': (failure or {}).get('sqlstate') == '23514' if scenario == 'transactional_rollback' else (failure or {}).get('code') == expect,
                  'database_unchanged_or_rolled_back': oracle.same_state(before, after)}
    row = {'scenario': scenario, 'pass': all(checks.values()), 'checks': checks, 'failure': failure, 'receipt': result}
    controls.write_json(directory / 'before.json', before); controls.write_json(directory / 'after.json', after)
    controls.write_json(directory / 'result.json', row); save_dump(database, directory)
    print('control ' + case.get('case', 'synthetic') + ' ' + scenario + ': ' + str(row['pass']), flush=True)
    return row


def mutant(database, case, defect, directory, schemas):
    directory.mkdir(parents=True, exist_ok=False); reset(database)
    ir, intervention = factory.authored(case['raw'], case['loader_service'], directory / 'fixtures', missing=defect == 'gate_bypass')
    plan = adapter.compile_projection(ir, intervention, schemas)
    receipt = adapter.execute(plan, database, directory / 'fixtures', directory / 'execution')
    schema, table = target(ir); qualified = ops.ident(schema) + '.' + ops.ident(table)
    before = oracle.observe(database, schema, table); status = copy.deepcopy(receipt['load_status'])
    header, rows = oracle.expected_csv(case['raw'])
    if defect == 'fake_success_empty_target': database.sql('DELETE FROM ' + qualified)
    elif defect == 'corrupt_value': database.sql('UPDATE ' + qualified + ' SET ' + ops.ident(header[0]) + "='__corrupt__'")
    elif defect == 'drop_row': database.sql('DELETE FROM ' + qualified + ' WHERE ctid=(SELECT ctid FROM ' + qualified + ' LIMIT 1)')
    elif defect == 'wrong_schema': database.sql('ALTER TABLE ' + qualified + ' RENAME COLUMN ' + ops.ident(header[0]) + ' TO wrong_column')
    elif defect == 'wrong_status': status['success'] = False
    elif defect == 'gate_bypass':
        # Deliberately create a forbidden side effect. The independent gate
        # oracle must catch it; no adapter code is weakened for this mutant.
        database.sql('CREATE TABLE ' + qualified + ' (unexpected TEXT); INSERT INTO ' + qualified + " VALUES ('bypassed')")
    after = oracle.observe(database, schema, table)
    detected = not oracle.same_state(before, after) if defect == 'gate_bypass' else not oracle.check_loaded(after, case['raw'], status)['pass']
    row = {'defect': defect, 'detected': detected, 'mutated_status': status}
    controls.write_json(directory / 'source_projection.json', ir); controls.write_json(directory / 'intervention.json', intervention)
    controls.write_json(directory / 'before.json', before); controls.write_json(directory / 'after.json', after)
    controls.write_json(directory / 'result.json', row); save_dump(database, directory)
    print('mutant ' + case.get('case', 'synthetic') + ' ' + defect + ': detected=' + str(detected), flush=True)
    return row


def render(output, run):
    lines = ['# Authored CSV IR adapter controls', '', 'Status: ' + run['status'], '', run['design']['scope'], '',
        '| Public CSV source | Positive controls | Gate controls | Refusals | Mutants detected | Gate passed |', '|---|---:|---:|---:|---:|---|']
    for row in run['case_results']:
        lines.append('| ' + row['case'] + ' | ' + ' | '.join(str(row[k]) for k in ('positive_passes', 'gate_passes', 'refusal_passes', 'mutants_detected', 'control_gate_pass')) + ' |')
    if run.get('error'): lines += ['', 'Error: ' + run['error']]
    lines += ['', 'No saved model artifacts were executed or changed. Zero LLM calls. No new semantic score.',
        'Inspect per-trial projections, interventions, plan hashes, output schemas, receipts, before/after database observations and SQL dumps.',
        'Passing controls is a prerequisite to a separately frozen 54-IR reinspection/replay; the 54 direct-Argo cells remain a separate route.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--postgres-image', default='postgres:16'); args = parser.parse_args(argv)
    print('Verifying completed eligibility evidence and new authored adapter controls...', flush=True)
    p = prepare(); config = p['config']
    if args.dry_run:
        print(json.dumps({'cases': [c['case'] for c in p['cases']], 'positive_controls_per_source': len(config['positives']),
            'gate_controls_per_source': len(config['gates']), 'refusals_per_source': len(config['refusals']), 'mutants_per_source': len(config['mutants']),
            'verified_input_pins': len(p['hashes']), 'llm_calls': 0, 'saved_workflows_executed': 0}, indent=2)); return 0
    image = transport.image_info(args.postgres_image)
    output = ROOT / 'audit/outputs' / ('package_v2_csv_ir_adapter_controls__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    run = {'status': 'running', 'design': config, 'image': image, 'case_results': [], 'llm_calls': 0, 'saved_workflows_executed': 0,
           'environment': {'python': sys.version, 'jsonschema': importlib.metadata.version('jsonschema'), 'PyYAML': importlib.metadata.version('PyYAML')},
           'input_fingerprint': controls.fingerprint(p['hashes'])}
    controls.write_json(output / 'input_sha256.json', p['hashes']); controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    try:
        env = dict(os.environ); env['P2SF_POSTGRES_TEST_IMAGE'] = image['id']
        tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TEST)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
        if tests.returncode: raise ValueError('Adapter unit/integration verification failed; inspect verification.txt')
        with transport.Postgres(image) as database:
            run['server_version'] = database.server_version
            for case in p['cases']:
                directory = output / 'cases' / case['case']; directory.mkdir(parents=True)
                (directory / 'source.csv').write_bytes(case['raw']); controls.write_json(directory / 'schemas.json', p['schemas'])
                rows = [trial(database, case, scenario, directory / 'trials' / scenario, p['schemas'], config)
                        for scenario in config['positives'] + config['gates'] + config['refusals']]
                mutants = [mutant(database, case, name, directory / 'mutants' / name, p['schemas']) for name in config['mutants']]
                row = {'case': case['case'], 'positive_passes': sum(r['pass'] for r in rows if r['scenario'] in config['positives']),
                    'gate_passes': sum(r['pass'] for r in rows if r['scenario'] in config['gates']),
                    'refusal_passes': sum(r['pass'] for r in rows if r['scenario'] in config['refusals']),
                    'mutants_detected': sum(m['detected'] for m in mutants),
                    'control_gate_pass': all(r['pass'] for r in rows) and all(m['detected'] for m in mutants)}
                run['case_results'].append(row); controls.write_json(directory / 'result.json', row)
                controls.write_json(output / 'run.json', run)
                print(case['case'] + ': control_gate=' + str(row['control_gate_pass']), flush=True)
        prior.previous.coverage.frozen.parent.verify_hashes(output, run); run['source_inputs_unchanged'] = True
        run['status'] = 'complete' if len(run['case_results']) == len(p['cases']) and all(r['control_gate_pass'] for r in run['case_results']) else 'complete_controls_failed'
    except Exception as exc:
        run['status'] = 'infrastructure_or_control_error'; run['error'] = type(exc).__name__ + ': ' + str(exc)
        controls.write_json(output / 'run.json', run); render(output, run); raise
    controls.write_json(output / 'run.json', run); render(output, run)
    seal = {p.relative_to(output).as_posix(): controls.sha256(p) for p in output.rglob('*') if p.is_file()}
    controls.write_json(output / 'output_sha256.json', {'files': seal, 'output_fingerprint': controls.fingerprint(seal), 'seal_stage': 'end-of-run', 'self_excluded': 'output_sha256.json'})
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
