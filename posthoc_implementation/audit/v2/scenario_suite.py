"""Versioned evaluator-side scenario handoff and durable execution snapshots.

Only registered kernels run. Private predicates are read after output sealing;
no model, generated program, old scorer or private reference program is run.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil

import csv_ir_adapter as adapter
import csv_postgres_oracle as oracle
import csv_postgres_transport as transport
import scenario_alignment_v2 as metadata

VERSION = 'p2sf.scenario-suite/1'


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(adapter.ops.canonical_bytes(value))


def read(path): return json.loads(Path(path).read_text())


def files(root):
    return {p.relative_to(root).as_posix(): metadata.sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def equal(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def require(value, message):
    if not value: raise ValueError(message)


def spec(row, scenario, fixture_root, selector):
    """External input binding policy, independent of predicate expectations."""
    name = scenario.get('name'); params = scenario.get('parameters')
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', name), 'Unsafe scenario ID')
    require(isinstance(params, dict) and set(params) == {selector}, 'Every scenario parameter must have an explicit input binding')
    filename = params[selector]
    require(isinstance(filename, str) and filename not in ('', '.', '..') and Path(filename).name == filename and '\\' not in filename,
            'CSV selection must be one explicit fixture filename')
    require(not any(token in filename for token in ('{', '}', '$', '*', '?', '[', ']', '\0')), 'Filename templates and globs are not resolved')
    path = metadata.bounded.safe(fixture_root, filename)
    source = row['plan']; require(adapter.digest(source['source_ir']) == source['source_ir_sha256'], 'Source IR changed')
    require(adapter.digest({k: v for k, v in source.items() if k != 'plan_sha256'}) == source['plan_sha256'], 'Source plan changed')
    result = {'version': VERSION, 'cell_id': row['source']['id'], 'scenario_id': name, 'parameters': copy.deepcopy(params),
        'selector_parameter': selector, 'selected_filename': filename, 'selected_path': str(path),
        'selected_sha256': metadata.sha(path) if path.is_file() else 'MISSING',
        'fixture_root': str(Path(fixture_root).resolve()), 'fixture_inventory': metadata.tree(fixture_root),
        'source_ir_sha256': source['source_ir_sha256'], 'original_artifact_sha256': row['artifact_sha256'],
        'source_plan_sha256': source['plan_sha256'],
        'fixture_pool_policy': 'Treat reviewed fixtures as an input pool. Supply and mount only the CSV selected for the existing external CSV slot, not the whole pool. A missing selection supplies no CSV. This is a declared v2 resource/input interpretation, not equivalence to the old fixture-directory execution.',
        'intervention': 'The scenario parameter supplies the explicitly bound external CSV input slot. Absent selected files stay absent. Resource bytes, composition graph, business parameters, output IDs and schemas are preserved; no private predicate selects input values.'}
    result['spec_sha256'] = adapter.digest(result)
    return result


def validate_spec(value):
    require(value['version'] == VERSION and adapter.digest({k: v for k, v in value.items() if k != 'spec_sha256'}) == value['spec_sha256'], 'Scenario specification changed')
    require(value['parameters'] == {value['selector_parameter']: value['selected_filename']}, 'Scenario selector and parameter disagree')


def materialize(row, value, directory):
    validate_spec(value)
    require(row['source']['id'] == value['cell_id'] and row['plan']['source_ir_sha256'] == value['source_ir_sha256'] and
            row['plan']['plan_sha256'] == value['source_plan_sha256'] and row['artifact_sha256'] == value['original_artifact_sha256'], 'Scenario/source identity differs')
    require(adapter.digest(row['plan']['source_ir']) == value['source_ir_sha256'] and
            adapter.digest({k: v for k, v in row['plan'].items() if k != 'plan_sha256'}) == value['source_plan_sha256'], 'Source plan or IR changed')
    require(metadata.tree(value['fixture_root']) == value['fixture_inventory'], 'Reviewed fixture inventory changed')
    selected = Path(value['selected_path']); raw = selected.read_bytes() if selected.is_file() else None
    require((hashlib.sha256(raw).hexdigest() if raw is not None else 'MISSING') == value['selected_sha256'], 'Selected scenario input changed')
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    plan = copy.deepcopy(row['plan']); fixture_map = plan['intervention']['fixtures']
    csv_refs = sorted(ref for ref, e in fixture_map.items() if e['kind'] == 'csv')
    require(csv_refs and sum(e['kind'] == 'filesystem' for e in fixture_map.values()) == 1, 'Require explicit existing CSV and filesystem bindings')
    for ref, entry in fixture_map.items():
        original = Path(row['fixture_sources'][ref]); original_bytes = original.read_bytes()
        require(hashlib.sha256(original_bytes).hexdigest() == entry['sha256'], 'Original public fixture bytes changed')
        path = adapter.ops.inside(directory, entry['path']); path.parent.mkdir(parents=True, exist_ok=True)
        if entry['kind'] == 'csv':
            entry.update(sha256=value['selected_sha256'], selected_scenario_filename=value['selected_filename'])
            if raw is not None: path.write_bytes(raw)
        else: path.write_bytes(original_bytes)
        if entry['kind'] == 'filesystem': entry['files'] = {value['selected_filename']: csv_refs[0]}
    plan['intervention']['scenario_input'] = {k: value[k] for k in ('scenario_id', 'parameters', 'selected_filename', 'selected_sha256', 'spec_sha256')}
    plan = adapter.compile_projection(plan['source_ir'], plan['intervention'], plan['schemas'])
    require(plan['source_ir'] == row['plan']['source_ir'], 'Composition was modified')
    receipt = {'spec_sha256': value['spec_sha256'], 'parameters': value['parameters'], 'input_files': files(directory),
               'csv_paths': [fixture_map[r]['path'] for r in csv_refs], 'selected_sha256': value['selected_sha256']}
    return plan, receipt


def seal_snapshot(directory):
    snapshot = directory / 'output_snapshot'; mapping = files(snapshot)
    archive = {'version': VERSION, 'snapshot_root': 'output_snapshot', 'files': mapping, 'snapshot_sha256': adapter.digest(mapping)}
    write(directory / 'snapshot_manifest.json', archive)
    return archive


def execute(row, value, directory, image):
    """Execute one scenario and archive its real outputs before scoring."""
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    plan, receipt = materialize(row, value, directory / 'inputs')
    write(directory / 'scenario_spec.json', value); write(directory / 'invocation_plan.json', plan)
    snapshot = directory / 'output_snapshot'; result = None; error = None
    target = row['target']
    with transport.Postgres(image) as database:
        database.sql('CREATE SCHEMA IF NOT EXISTS ' + adapter.ops.ident(target['schema']))
        before = oracle.observe(database, target['schema'], target['table'])
        try: result = adapter.execute(plan, database, directory / 'inputs', snapshot)
        except adapter.Error as exc: error = {'code': exc.code, 'message': str(exc)}
        except FileNotFoundError as exc: error = {'code': 'unavailable_bound_input', 'message': str(exc)}
        except transport.DatabaseError as exc:
            if exc.sqlstate is None or exc.sqlstate[:2] not in ('22', '23', '42', '0A'): raise
            error = {'code': 'database_operation_error', 'sqlstate': exc.sqlstate, 'message': str(exc)}
        after = oracle.observe(database, target['schema'], target['table'])
        snapshot.mkdir(parents=True, exist_ok=True)
        write(snapshot / 'database/before.json', before); write(snapshot / 'database/after.json', after)
        (snapshot / 'database/target.sql').write_text(transport.docker('exec', database.name, 'pg_dump', '-U', 'postgres', '-d', 'p2sf_controls',
            '--schema=' + target['schema'], '--no-owner', '--no-privileges'))
        require(files(directory / 'inputs') == receipt['input_files'], 'Inputs changed during execution')
        shutil.copytree(directory / 'inputs', snapshot / 'supplied_inputs')
        write(snapshot / 'input_receipt.json', receipt); write(snapshot / 'invocation_plan.json', plan)
        write(snapshot / 'execution_provenance.json', {'version': VERSION, 'cell_id': value['cell_id'], 'scenario_id': value['scenario_id'],
            'parameters': value['parameters'], 'spec_sha256': value['spec_sha256'], 'source_ir_sha256': value['source_ir_sha256'],
            'original_artifact_sha256': value['original_artifact_sha256'], 'plan_sha256': plan['plan_sha256'],
            'state': 'completed' if result is not None and error is None else 'failed', 'execution_error': error,
            'adapter_receipt': result, 'image': image, 'server_version': database.server_version,
            'target': target, 'snapshot_stage': 'actual execution outputs retained before predicate evaluation'})
    seal_snapshot(directory)
    return directory


def verify_snapshot(directory, expected):
    validate_spec(expected)
    directory = Path(directory); archive = read(directory / 'snapshot_manifest.json'); snapshot = directory / 'output_snapshot'
    require(archive['version'] == VERSION and archive['snapshot_root'] == 'output_snapshot', 'Unsupported snapshot manifest')
    require(files(snapshot) == archive['files'] and adapter.digest(archive['files']) == archive['snapshot_sha256'], 'Snapshot files or seal changed')
    provenance = read(snapshot / 'execution_provenance.json'); receipt = read(snapshot / 'input_receipt.json'); plan = read(snapshot / 'invocation_plan.json')
    for key in ('cell_id', 'scenario_id', 'parameters', 'spec_sha256', 'source_ir_sha256', 'original_artifact_sha256'):
        require(equal(provenance[key], expected[key]), 'Snapshot identity/input provenance differs: ' + key)
    require(receipt['spec_sha256'] == expected['spec_sha256'] and equal(receipt['parameters'], expected['parameters']) and
            receipt['selected_sha256'] == expected['selected_sha256'], 'Scenario parameter handoff differs')
    require(files(snapshot / 'supplied_inputs') == receipt['input_files'], 'Supplied input snapshot differs')
    for relative in receipt['csv_paths']:
        path = adapter.ops.inside(snapshot / 'supplied_inputs', relative)
        actual = metadata.sha(path) if path.is_file() else 'MISSING'
        require(actual == expected['selected_sha256'], 'Runner ignored selected CSV input')
    mounted = files(snapshot / 'mounted_files')
    expected_mount = {} if expected['selected_sha256'] == 'MISSING' else {expected['selected_filename']: expected['selected_sha256']}
    require(mounted == expected_mount, 'Runner mounted different scenario data')
    require(adapter.digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) == provenance['plan_sha256'] == plan['plan_sha256'], 'Execution plan changed')
    require(adapter.digest(plan['source_ir']) == expected['source_ir_sha256'], 'Source IR differs')
    require(plan['intervention']['scenario_input']['spec_sha256'] == expected['spec_sha256'], 'Execution plan used different scenario')
    return snapshot, provenance, receipt


def validate_assertions(definitions):
    require(isinstance(definitions, list) and definitions, 'Empty assertion set cannot pass')
    names = [d.get('assertion_id') for d in definitions]
    require(all(isinstance(n, str) and n for n in names) and len(set(names)) == len(names), 'Missing or duplicate assertion IDs')
    for d in definitions:
        kind = d.get('type'); require(kind in ('json_path_equals', 'file_absent', 'file_exists'), 'Unsupported reviewed predicate')
        metadata.bounded.safe(Path('/snapshot-placeholder'), d['path'])
        require(d['path'].startswith('artifacts/'), 'Predicates must address artifact files')
        if kind == 'json_path_equals':
            require(isinstance(d.get('json_path'), str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)*', d['json_path']) and
                    'expected' in d, 'Unsupported JSON predicate path/value')


def predicate(definition, snapshot):
    path = metadata.bounded.safe(snapshot, definition['path']); kind = definition['type']
    if kind == 'file_absent': return not path.exists()
    if kind == 'file_exists': return path.is_file() and path.stat().st_size > 0
    if not path.is_file(): return False
    value = read(path)
    for key in definition['json_path'].split('.'):
        if not isinstance(value, dict) or key not in value: return False
        value = value[key]
    return equal(value, definition['expected'])


def score(directory, expected, definitions):
    """Read sealed outputs only; no predicates can change an execution input."""
    validate_assertions(definitions)
    try: snapshot, provenance, input_receipt = verify_snapshot(directory, expected)
    except (ValueError, KeyError, OSError) as exc:
        return {'scenario_id': expected['scenario_id'], 'spec_sha256': expected['spec_sha256'], 'pass': False,
                'snapshot_verified': False, 'error': str(exc), 'assertions': [], 'business_checks': {}}
    completed = provenance['state'] == 'completed' and provenance['execution_error'] is None
    checks = [{'assertion_id': d['assertion_id'], 'pass': completed and predicate(d, snapshot)} for d in definitions]
    before, after = read(snapshot / 'database/before.json'), read(snapshot / 'database/after.json')
    execution = provenance['adapter_receipt'] or {}; status = execution.get('load_status') or {}
    if expected['selected_sha256'] == 'MISSING':
        business = {'execution_completed': completed, 'loader_not_called': execution.get('loader_called') is False,
                    'gate_skipped': execution.get('state') == 'skipped_missing_input', 'database_unchanged': oracle.same_state(before, after)}
    else:
        data = adapter.ops.inside(snapshot / 'supplied_inputs', input_receipt['csv_paths'][0]).read_bytes()
        business = oracle.check_loaded(after, data, status)['checks']
        business.update(execution_completed=completed, loaded=execution.get('state') == 'loaded',
                        correct_public_count=status.get('rows_loaded') == len(oracle.expected_csv(data)[1]))
    return {'scenario_id': expected['scenario_id'], 'spec_sha256': expected['spec_sha256'], 'snapshot_verified': True,
        'snapshot_sha256': read(Path(directory) / 'snapshot_manifest.json')['snapshot_sha256'], 'assertions': checks,
        'business_checks': business, 'execution_error': provenance['execution_error'],
        'pass': completed and all(c['pass'] for c in checks) and all(business.values())}


def aggregate(specs, results):
    expected = [s['scenario_id'] for s in specs]; actual = [r['scenario_id'] for r in results]
    require(expected and len(set(expected)) == len(expected), 'Nonempty unique required scenarios needed')
    unique = len(set(actual)) == len(actual)
    coverage = unique and set(expected) == set(actual)
    signatures = {s['scenario_id']: s['spec_sha256'] for s in specs}
    identities = all(r['scenario_id'] in signatures and r['spec_sha256'] == signatures[r['scenario_id']] for r in results)
    nonempty = all(r.get('assertions') and r.get('business_checks') for r in results)
    return {'required_scenarios': len(expected), 'recorded_scenarios': len(actual), 'unique_scenarios': unique,
        'complete_coverage': coverage, 'identity_matches': identities, 'nonvacuous_checks': bool(results) and nonempty,
        'passed_scenarios': sum(r['pass'] is True for r in results),
        'suite_pass': coverage and identities and nonempty and all(r['pass'] is True and r.get('snapshot_verified') is True for r in results)}
