#!/usr/bin/env python3
"""User-run, real PostgreSQL reference controls; no LLM or model runner."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import io
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'audit/v2')); sys.path.insert(0, str(ROOT / 'audit'))
import audit_v2_cross_task_coverage as coverage
import csv_postgres_ops as ops
import csv_postgres_oracle as oracle
import csv_postgres_transport as transport

controls, replay = coverage.controls, coverage.replay
CONFIG = ROOT / 'audit/v2/csv_postgres_controls.v1.json'
TESTS = ROOT / 'tests/unit/test_v2_csv_postgres_controls.py'
DOC = ROOT / 'audit/v2/CSV_POSTGRES_CONTROLS.md'


def prepare():
    config = replay.read_json(CONFIG)
    if config['allowed_write_modes'] != ['append', 'replace'] or config['backend_version'] != ops.VERSION:
        raise ValueError('Declared backend subset differs')
    root = ROOT / config['coverage_run']; source = replay.read_json(root / 'run.json')
    if source['status'] != 'complete' or source.get('source_inputs_unchanged') is not True:
        raise ValueError('Completed unchanged coverage audit required')
    # Verify the completed snapshot directly. Do not dynamically alter or
    # rerun a frozen model runner's imported-module inventory for this phase.
    hashes = coverage.frozen.parent.verify_hashes(root, source)
    if len(source['completed_cases']) != 110 or set(source['completed_cases']) != set(source['cases']):
        raise ValueError('Coverage task roster differs')
    for name, saved in source['completed_cases'].items():
        path = Path(saved['path'])
        if controls.sha256(path) != saved['sha256'] or replay.read_json(path)['case'] != name:
            raise ValueError('Coverage checkpoint changed')
    baseline = ROOT / source['design']['public_baseline']
    public_cases = []
    paths = [Path(__file__).resolve(), CONFIG, TESTS, DOC, Path(ops.__file__), Path(oracle.__file__), Path(transport.__file__),
             root / 'run.json', root / 'input_sha256.json', *[Path(v['path']) for v in source['completed_cases'].values()]]
    for spec in config['cases']:
        case = spec['case']
        if case not in source['cases']: raise ValueError('Undeclared control candidate')
        workspace = baseline / case / 'public_workspace' / case
        path = coverage.analysis.contained(workspace, spec['source_csv'])
        raw = path.read_bytes(); header, _ = oracle.expected_csv(raw)
        if not header or len(header) != len(set(header)): raise ValueError('Invalid nominal public CSV header')
        contract = {'version': ops.VERSION, 'case': case, 'loader_service': spec['loader_service'],
            'required_columns': header, 'target_table': config['target_table'], 'resource': config['resource'],
            'schema_policy': config['schema_policy'], 'scope': config['scope'],
            'original_source_csv': spec['source_csv'], 'source_csv_sha256': controls.sha256(path),
            'file_location_resource': {'driver': 'fixture-filesystem', 'root': '.'},
            'sensor_parameters': {'location_type': 'filesystem', 'path': 'source.csv', 'availability_condition': 'exists'}}
        descriptor = workspace / 'catalog/services' / (spec['loader_service'] + '.yaml')
        reviewed = controls.load(descriptor)
        implementation = reviewed.get('invocation', {}).get('implementation_ref')
        contract['original_implementation_ref'] = implementation
        contract['original_implementation_present_under_workspace'] = bool(implementation and (ROOT / implementation).exists())
        public_cases.append({'case': case, 'source': path, 'raw': raw, 'contract': contract})
        paths += [path, descriptor, workspace / 'task.md', workspace / 'workspace.yaml']
    for path in paths:
        name, sha = str(path.resolve()), controls.sha256(path)
        if name in hashes and hashes[name] != sha: raise ValueError('Pinned input differs: ' + name)
        hashes[name] = sha
    return {'design': config, 'cases': public_cases, 'hashes': hashes}


def csv_bytes(rows):
    stream = io.StringIO(newline=''); csv.writer(stream, lineterminator='\n').writerows(rows)
    return stream.getvalue().encode()


def variant(raw, scenario):
    header, rows = oracle.expected_csv(raw); data = copy.deepcopy(rows)
    if scenario == 'extra_row': data.append(['added_record'] + data[0][1:])
    elif scenario == 'changed_value': data[0][-1] = '__changed_public_value__'
    elif scenario == 'reordered_rows': data.reverse()
    elif scenario == 'quoted_multiline': data[0][-1] = 'Unicode Δ, quoted "value"\nline; SELECT \'literal\''
    elif scenario in ('empty_allowed', 'empty_rejected'): data = []
    elif scenario == 'missing_column': header = header[:-1]; data = [r[:-1] for r in data]
    elif scenario == 'ragged_row': data[0].append('extra_cell')
    elif scenario == 'missing_file': return None
    return csv_bytes([header, *data])


def reset(database, resource):
    schema = ops.ident(resource['schema'])
    database.sql('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE; CREATE SCHEMA ' + schema + ';')


def trial(database, item, scenario, directory, config):
    directory.mkdir(parents=True, exist_ok=False)
    contract = item['contract']; resource = config['resource']; table = config['target_table']
    reset(database, resource)
    raw = variant(item['raw'], scenario)
    if raw is not None: (directory / 'input.csv').write_bytes(raw)
    controls.write_json(directory / 'contract.json', contract)
    relation = ops.ident(resource['schema']) + '.' + ops.ident(table)
    if scenario == 'existing_schema_mismatch':
        database.sql('CREATE TABLE ' + relation + ' (wrong_column TEXT NOT NULL); INSERT INTO ' + relation + " VALUES ('prior_state');")
    elif scenario == 'transactional_rollback':
        # Establish real committed prior state, then add a public test-target
        # constraint so a later INSERT fails after replace's DELETE begins.
        ops.execute_control(database, resource, directory / 'initial', item['raw'], contract)
        first = contract['required_columns'][0]
        database.sql('ALTER TABLE ' + relation + ' ADD CONSTRAINT reject_control_value CHECK (' + ops.ident(first) + " <> '__reject_control__');")
        header, rows = oracle.expected_csv(raw); rows[-1][0] = '__reject_control__'; raw = csv_bytes([header, *rows])
        (directory / 'input.csv').write_bytes(raw)
    before = oracle.observe(database, resource['schema'], table)
    mode = 'upsert' if scenario == 'unsupported_mode' else ('append' if scenario == 'repeat_append' else 'replace')
    result = None; failure = None
    try:
        result = ops.execute_control(database, resource, directory / 'execution', raw, contract,
            mode=mode, fail_on_empty=scenario != 'empty_allowed', metadata_defect=scenario == 'metadata_hash_mismatch')
        if scenario in ('repeat_append', 'repeat_replace'):
            second = raw
            if scenario == 'repeat_replace': second = variant(raw, 'changed_value')
            (directory / 'second_input.csv').write_bytes(second)
            result = ops.execute_control(database, resource, directory / 'repeat', second, contract, mode=mode)
            if scenario == 'repeat_replace': raw = second
    except ops.ContractError as exc: failure = {'type': 'public_contract_refusal', 'code': exc.code, 'message': str(exc)}
    except transport.DatabaseError as exc: failure = {'type': 'database_error', 'sqlstate': exc.sqlstate, 'message': str(exc)}
    after = oracle.observe(database, resource['schema'], table)
    if scenario in config['positive_cases']:
        (directory / 'expected_source.csv').write_bytes(raw)
        checked = oracle.check_loaded(after, raw, (result or {}).get('load_status', {}), repetitions=2 if scenario == 'repeat_append' else 1)
        checked['checks']['no_unexpected_refusal'] = failure is None
    elif scenario == 'missing_file':
        checked = {'checks': {'missing_file_gate': (result or {}).get('state') == 'skipped_missing_input',
            'loader_not_called': (result or {}).get('loader_called') is False, 'database_unchanged': oracle.same_state(before, after)}}
    else:
        expected = {'missing_column': 'csv_validation_failed', 'ragged_row': 'csv_validation_failed',
            'empty_rejected': 'csv_validation_failed', 'unsupported_mode': 'unsupported_write_mode',
            'existing_schema_mismatch': 'target_schema_mismatch', 'metadata_hash_mismatch': 'dataset_hash_mismatch'}
        right_reason = ((failure or {}).get('sqlstate') == '23514' if scenario == 'transactional_rollback'
                        else (failure or {}).get('code') == expected[scenario])
        checked = {'checks': {'expected_refusal_reason': right_reason, 'target_state_unchanged_or_rolled_back': oracle.same_state(before, after)}}
    checked['pass'] = all(checked['checks'].values())
    controls.write_json(directory / 'before.json', before); controls.write_json(directory / 'after.json', after)
    controls.write_json(directory / 'result.json', {'scenario': scenario, 'execution': result, 'failure': failure, **checked})
    (directory / 'target.sql').write_text(transport.docker('exec', database.name, 'pg_dump', '-U', 'postgres', '-d', 'p2sf_controls',
        '--schema=' + resource['schema'], '--no-owner', '--no-privileges'))
    return {'scenario': scenario, **checked}


def mutant(database, item, defect, directory, config):
    directory.mkdir(parents=True, exist_ok=False); resource = config['resource']; table = config['target_table']
    reset(database, resource); contract = item['contract']; relation = ops.ident(resource['schema']) + '.' + ops.ident(table)
    result = ops.execute_control(database, resource, directory / 'execution', None if defect == 'gate_bypass' else item['raw'], contract)
    if defect == 'gate_bypass':
        ops.execute_control(database, resource, directory / 'bypassed', item['raw'], contract)
    elif defect == 'fake_success_empty_target': database.sql('DELETE FROM ' + relation)
    elif defect == 'corrupt_value': database.sql('UPDATE ' + relation + ' SET ' + ops.ident(contract['required_columns'][-1]) + "='__corrupt__' WHERE ctid=(SELECT ctid FROM " + relation + ' LIMIT 1)')
    elif defect == 'drop_row': database.sql('DELETE FROM ' + relation + ' WHERE ctid=(SELECT ctid FROM ' + relation + ' LIMIT 1)')
    elif defect == 'schema_corruption': database.sql('ALTER TABLE ' + relation + ' RENAME COLUMN ' + ops.ident(contract['required_columns'][0]) + ' TO corrupted_column')
    else: raise ValueError('Undeclared mutant')
    after = oracle.observe(database, resource['schema'], table)
    checked = ({'pass': not after['exists'], 'checks': {'no_load_after_missing_file': not after['exists']}} if defect == 'gate_bypass'
               else oracle.check_loaded(after, item['raw'], result['load_status']))
    record = {'defect': defect, 'detected': not checked['pass'], 'oracle': checked, 'observed_database': after}
    controls.write_json(directory / 'result.json', record)
    (directory / 'target.sql').write_text(transport.docker('exec', database.name, 'pg_dump', '-U', 'postgres', '-d', 'p2sf_controls',
        '--schema=' + resource['schema'], '--no-owner', '--no-privileges'))
    return record


def render(output, run):
    lines = ['# Real PostgreSQL CSV reference controls', '', f"Protocol {run['protocol_version']}; status {run['status']}.",
        'Zero LLM calls. New mechanism controls using public source CSVs; no model-method or original G6-Assert score replacement.', '',
        '| Source task | Positive controls | Missing-file gate | Expected refusals | Mutants detected | Control gate |',
        '|---|---:|---:|---:|---:|---|']
    for row in run['case_results']:
        lines.append(f"| {row['case']} | {row['positive_passes']}/{row['positive_total']} | {row['gate_passes']}/1 | {row['refusal_passes']}/{row['refusal_total']} | {row['mutants_detected']}/{row['mutant_total']} | {row['control_gate_pass']} |")
    lines += ['', 'Actual PostgreSQL 16, Unix-socket clients in a disposable network-isolated container. New public test target; original mock/absent resources are not reinterpreted.',
        'CSV strings remain TEXT; bounded local-file detection, append and replace only. No SFTP, scheduling, typed transformations, filtering, upsert or full original-task equivalence claim.',
        'Expected rows come from independent CSV parsing and direct database reads. Status flags alone cannot pass.',
        'Each case uses many control variants; these are two source datasets, not dozens of independent pipelines.',
        'Database snapshots and SQL dumps are retained per trial. Original data, freezes and all previous results are unchanged.', '']
    (output / 'summary.md').write_text('\n'.join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--postgres-image', default='postgres:16')
    args = parser.parse_args(argv)
    print('Verifying public CSVs, completed coverage evidence and the new database control contract...', flush=True)
    p = prepare(); config = p['design']
    if args.dry_run:
        print(json.dumps({'cases': [c['case'] for c in p['cases']], 'engine': 'PostgreSQL 16', 'write_modes': config['allowed_write_modes'],
            'positive_controls_per_source': len(config['positive_cases']), 'mutants_per_source': len(config['mutants']),
            'llm_calls': 0, 'model_workflow_executions': 0, 'source_scores_replaced': False}, indent=2)); return 0
    image = transport.image_info(args.postgres_image)
    output = ROOT / 'audit/outputs' / ('package_v2_csv_postgres_controls__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '__' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    run = {'protocol_version': config['protocol_version'], 'design': config, 'status': 'running', 'llm_calls': 0,
           'model_workflow_executions': 0, 'case_results': [], 'image': image, 'input_fingerprint': controls.fingerprint(p['hashes'])}
    controls.write_json(output / 'input_sha256.json', p['hashes']); controls.write_json(output / 'run.json', run)
    print('Output: ' + str(output), flush=True)
    env = dict(os.environ); env['P2SF_POSTGRES_TEST_IMAGE'] = image['id']
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(TESTS)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    (output / 'verification.txt').write_text(tests.stdout + tests.stderr)
    if tests.returncode: raise ValueError('PostgreSQL integration verification failed; inspect verification.txt')
    try:
        with transport.Postgres(image) as database:
            run['server_version'] = database.server_version
            for item in p['cases']:
                case = item['case']; case_root = output / 'cases' / case
                public = case_root / 'public_fixture'; public.mkdir(parents=True)
                (public / 'source.csv').write_bytes(item['raw']); controls.write_json(public / 'contract.json', item['contract'])
                controls.write_json(public / 'target_database.json', config['resource'])
                controls.write_json(public / 'file_location.json', item['contract']['file_location_resource'])
                refusals = config['refusal_cases'] + (config['tabular_only_refusals'] if item['contract']['loader_service'] == ops.TABULAR else [])
                results = [trial(database, item, name, case_root / 'trials' / name, config)
                           for name in config['positive_cases'] + config['gate_cases'] + refusals]
                mutants = [mutant(database, item, name, case_root / 'mutants' / name, config) for name in config['mutants']]
                row = {'case': case, 'positive_total': len(config['positive_cases']), 'positive_passes': sum(r['pass'] for r in results if r['scenario'] in config['positive_cases']),
                    'gate_passes': sum(r['pass'] for r in results if r['scenario'] in config['gate_cases']),
                    'refusal_total': len(refusals), 'refusal_passes': sum(r['pass'] for r in results if r['scenario'] in refusals),
                    'mutant_total': len(mutants), 'mutants_detected': sum(m['detected'] for m in mutants),
                    'control_gate_pass': all(r['pass'] for r in results) and all(m['detected'] for m in mutants)}
                controls.write_json(case_root / 'result.json', row); run['case_results'].append(row)
                controls.write_json(output / 'run.json', run)
                print(case + ': control_gate=' + str(row['control_gate_pass']), flush=True)
    except Exception as exc:
        run['status'] = 'infrastructure_or_control_error'; run['error'] = type(exc).__name__ + ': ' + str(exc)
        controls.write_json(output / 'run.json', run); render(output, run); raise
    coverage.frozen.parent.verify_hashes(output, run)
    run['source_inputs_unchanged'] = True
    run['status'] = 'complete' if len(run['case_results']) == len(p['cases']) and all(r['control_gate_pass'] for r in run['case_results']) else 'complete_controls_failed'
    controls.write_json(output / 'run.json', run); render(output, run)
    print(run['status'] + ': ' + str(output / 'summary.md'), flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__': raise SystemExit(main())
