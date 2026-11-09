#!/usr/bin/env python3
"""Complete local workflow mechanism controls, never original-corpus scores."""
from __future__ import annotations

import argparse
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
import run_v2_model_replay as parent
sys.path.insert(0, str(ROOT / 'audit/v2'))
import workflow_executor as engine
import prompt_context
from jsonschema import Draft202012Validator

controls, replay, ports = parent.controls, parent.replay, parent.executor
CONFIG = ROOT / 'audit/v2/family_controls.json'
TESTS = ROOT / 'tests/unit/test_v2_family_controls.py'
FILES = list(dict.fromkeys([Path(__file__).resolve(), CONFIG, TESTS,
    ROOT / 'audit/v2/workflow_executor.py', ROOT / 'audit/v2/prompt_context.py',
    ROOT / 'audit/v2/FAMILY_CONTROLS.md', ROOT / 'scripts/run_v2_model_replay.py', *parent.IMPLEMENTATION]))


def make_plan(header):
    """New public control composition; never extracted from gold IR/answers."""
    artifacts = [
        {'artifact_id': 'location', 'producer': None, 'fixture_ref': 'fixtures/inputs/location.json', 'suffix': '.json'},
        {'artifact_id': 'source', 'producer': None, 'fixture_ref': 'fixtures/inputs/source.csv', 'suffix': '.csv'}]
    bindings = []
    specs = [('detect', engine.SENSOR, {'file_location_resource': 'location'},
              {'availability_decision': 'decision', 'check_status': 'sensor_status'},
              {'location_type': 'filesystem', 'path': 'source.csv', 'availability_condition': 'exists'}),
             ('validate', engine.CSV, {'csv_file': 'source'},
              {'validated_dataset': 'dataset', 'validated_data_object': 'metadata', 'validation_status': 'validation_status'},
              {'output_path': '/workspace/artifacts/metadata.json', 'required_columns': header,
               'has_header': True, 'fail_on_empty': True}),
             ('export', engine.EXPORT, {'structured_json': 'dataset'},
              {'csv_file': 'exported', 'export_status': 'export_status'},
              {'output_filename': '/data/roundtrip.csv', 'columns': header, 'include_header': True})]
    for intent, service, ins, outs, parameters in specs:
        for port, identity in outs.items():
            artifacts.append({'artifact_id': identity, 'producer': intent,
                              'suffix': '.csv' if port == 'csv_file' else '.json'})
        bindings.append({'intent_id': intent, 'service_id': service, 'service_version': '1.0.0',
            'input_bindings': [{'port': p, 'artifact_id': a} for p, a in ins.items()],
            'output_bindings': [{'port': p, 'artifact_id': a} for p, a in outs.items()],
            'parameter_bindings': parameters})
    return {'workflow_id': 'local_csv_roundtrip', 'contract_version': '2.1.0', 'artifacts': artifacts, 'bindings': bindings,
            'edges': [{'from': 'detect', 'to': 'validate'}, {'from': 'validate', 'to': 'export'}],
            'gates': [{'artifact_id': 'decision', 'field': 'available', 'equals': True, 'targets': ['validate', 'export']}]}


def table(raw: bytes):
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8')), strict=True))
    if len(rows) < 2 or len(rows[0]) < 2 or any(len(row) != len(rows[0]) for row in rows[1:]):
        raise ValueError('Controls require a non-empty rectangular multi-column public CSV')
    return rows


def encode(rows):
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator='\n').writerows(rows)
    return stream.getvalue().encode('utf-8')


def prepare_fixtures(raw: bytes, root: Path, names: list):
    original = table(raw)
    for name in names:
        destination = root / 'scenarios' / name
        destination.mkdir(parents=True, exist_ok=False)
        (destination / 'location.json').write_text('{"driver":"fixture-filesystem","root":"."}\n')
        rows = copy.deepcopy(original)
        if name == 'missing_file':
            continue
        if name == 'extra_row':
            rows.append(copy.deepcopy(rows[-1]))
            rows[-1][0] += '__extra'
        elif name == 'changed_value':
            rows[1][-1] += '__changed'
        elif name == 'missing_column':
            rows = [r[:-1] for r in rows]
        elif name != 'nominal':
            raise ValueError('Unknown declared scenario')
        (destination / 'source.csv').write_bytes(encode(rows))


def install(plan: dict, root: Path, fixture_source: Path, scenarios: list):
    scripts = root / 'runtime/scripts'
    scripts.mkdir(parents=True)
    for path in [ROOT / 'audit/v2/workflow_executor.py', ROOT / 'audit/v2/service_executor.py',
                 ROOT / 'audit/service_executor_v3.py', ROOT / 'audit/retention_adapter.py']:
        shutil.copy2(path, scripts / path.name)
    controls.write_json(scripts / 'plan.json', plan)
    (scripts / 'workflow.py').write_text(
        'import argparse,json\nfrom pathlib import Path\nfrom workflow_executor import execute\n'
        'p=argparse.ArgumentParser();p.add_argument("--workspace",type=Path);p.add_argument("--fixtures",type=Path)\n'
        'a=p.parse_args()\nr=execute(json.loads(Path(__file__).with_name("plan.json").read_text()),a.workspace,a.fixtures)\n'
        'print(json.dumps(r))\nraise SystemExit(0 if r["workflow_status"]=="completed" else 2)\n')
    shutil.copytree(fixture_source, root / 'fixtures')
    manifest = {'runtime_manifest_version': '0.1.0', 'pipeline_id': 'v2_local_workflow_control',
                'image': 'python:3.12-slim', 'workflow_parameters': [],
                'tasks': [{'intent_id': 'workflow', 'script': 'scripts/workflow.py',
                    'arguments': ['--workspace', '{workspace}', '--fixtures', '{fixtures}'], 'retries': 0}],
                'scenarios': [{'name': name, 'parameters': {}, 'fixture_root': 'fixtures/scenarios/' + name} for name in scenarios]}
    (root / 'runtime/manifest.yaml').write_text(controls.yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def public_schemas():
    result = {}
    for service in engine.SUPPORTED:
        descriptor = controls.load(controls.BENCHMARK / 'catalog/snapshots/0.1.0/services' / (service + '.yaml'))
        for contract in descriptor.get('contracts', []):
            if contract.get('type') == 'json_schema' and contract.get('applies_to') == 'output':
                try:
                    result[service, contract['target']] = json.loads(contract['expression'])
                except (ValueError, KeyError):
                    raise ValueError('Public output schema is not an explicit JSON schema')
    return result


def evaluate(result: dict, fixture_root: Path, plan: dict, scenario: str, schemas=None):
    """Independent relation oracle: csv.reader values, actual output, and trace.

    No gold assertions, constant expected row counts, or service compute calls.
    """
    snapshot = result['_snapshot']
    checks = []
    def check(name, ok):
        checks.append({'check': name, 'pass': bool(ok)})
    try:
        trace = json.loads(snapshot['logs/workflow_trace.json'])
        states = trace['states']
        if scenario == 'missing_file':
            check('gated_tasks_not_executed', states == {'detect': 'executed', 'validate': 'skipped', 'export': 'skipped'})
            check('availability_false', json.loads(snapshot['artifacts/decision.json'])['available'] is False)
            check('no_downstream_artifacts', not any(k in snapshot for k in ['artifacts/exported.csv', 'artifacts/dataset.json', 'artifacts/export_status.json']))
            check('no_workflow_error', trace['workflow_status'] == 'completed' and not result['_errors'])
        elif scenario == 'missing_column':
            check('validation_rejects_before_export', states == {'detect': 'executed', 'validate': 'failed', 'export': 'skipped'})
            check('specific_schema_error', any('missing required columns' in t.get('error', '') for t in trace['trace']))
            check('no_export_after_rejection', 'artifacts/exported.csv' not in snapshot)
        else:
            expected = table((fixture_root / 'source.csv').read_bytes())
            actual = list(csv.reader(io.StringIO(snapshot['artifacts/exported.csv'].decode()), strict=True))
            check('all_steps_executed', states == {'detect': 'executed', 'validate': 'executed', 'export': 'executed'})
            check('workflow_completed', trace['workflow_status'] == 'completed' and not result['_errors'])
            check('all_exported_values_equal_input', actual == expected)
            dataset = json.loads(snapshot['artifacts/dataset.json'])
            check('upstream_rows_reach_exporter', dataset['rows'] == [dict(zip(expected[0], row)) for row in expected[1:]])
            check('counts_equal_actual_input', dataset['row_count'] == len(expected) - 1
                  and json.loads(snapshot['artifacts/export_status.json'])['rows_written'] == len(expected) - 1)
            metadata = json.loads(snapshot['artifacts/metadata.json'])
            check('metadata_describes_actual_dataset', metadata['record_count'] == len(expected) - 1
                  and metadata['columns'] == expected[0])
            check('operation_statuses_agree_with_execution', all(json.loads(snapshot['artifacts/' + name + '.json'])['success'] is True
                  for name in ('sensor_status', 'validation_status', 'export_status')))
            check('sensor_reports_actual_file_presence', json.loads(snapshot['artifacts/decision.json'])['available'] is True)
        if schemas:
            artifacts = {a['artifact_id']: a for a in plan['artifacts']}
            for binding in plan['bindings']:
                if states.get(binding['intent_id']) != 'executed':
                    continue
                for output in binding['output_bindings']:
                    schema = schemas.get((binding['service_id'], output['port']))
                    if schema:
                        path = 'artifacts/' + output['artifact_id'] + artifacts[output['artifact_id']]['suffix']
                        Draft202012Validator(schema).validate(json.loads(snapshot[path]))
            check('public_output_schemas', True)
    except Exception as exc:
        checks.append({'check': 'evaluation_error', 'pass': False, 'error': f'{type(exc).__name__}: {exc}'})
    return {'pass': bool(checks) and all(c['pass'] for c in checks), 'checks': checks,
            'transport_errors': result['_errors'], 'scenario': scenario}


def run_source(source: Path, destination: Path, policy: dict):
    raw = source.read_bytes()
    plan = make_plan(table(raw)[0])
    controls.write_json(destination / 'control_plan.json', plan)
    prepare_fixtures(raw, destination / 'public_inputs/fixtures', policy['scenarios'])
    # Preview/generation context includes only nominal public inputs, not the
    # changed-input/negative scenarios used by the evaluator.
    preview = destination / 'generation_public_inputs/fixtures/inputs'
    preview.mkdir(parents=True)
    shutil.copy2(destination / 'public_inputs/fixtures/scenarios/nominal/source.csv', preview / 'source.csv')
    shutil.copy2(destination / 'public_inputs/fixtures/scenarios/nominal/location.json', preview / 'location.json')
    (destination / 'generation_public_context.txt').write_text(prompt_context.render_context(preview.parents[1]))
    manifest = install(plan, destination / 'execution_instance', destination / 'public_inputs/fixtures', policy['scenarios'])
    results = controls._execute_scenarios(destination / 'execution_instance', manifest, sandbox_generated=True)
    controls.persist_snapshots(results, destination / 'execution')
    schemas = public_schemas()
    outcomes = {r['scenario']: evaluate(r, destination / 'public_inputs/fixtures/scenarios' / r['scenario'], plan, r['scenario'], schemas)
                for r in results}
    mutations = {}
    nominal = next(r for r in results if r['scenario'] == 'nominal')
    for mode in ['constant_export', 'corrupt_export_value']:
        mutant = copy.deepcopy(nominal)
        rows = list(csv.reader(io.StringIO(mutant['_snapshot']['artifacts/exported.csv'].decode())))
        if mode == 'constant_export':
            rows = rows[:1]
        else:
            rows[1][-1] += '__wrong'
        mutant['_snapshot']['artifacts/exported.csv'] = encode(rows)
        controls.persist_snapshots([mutant], destination / 'mutations' / mode)
        evaluation = evaluate(mutant, destination / 'public_inputs/fixtures/scenarios/nominal', plan, 'nominal', schemas)
        mutations[mode] = {'detected': not evaluation['pass'], 'evaluation': evaluation}
    bypass = copy.deepcopy(plan)
    bypass['gates'] = []
    bypass_manifest = install(bypass, destination / 'gate_bypass_instance', destination / 'public_inputs/fixtures', ['missing_file'])
    bypass_results = controls._execute_scenarios(destination / 'gate_bypass_instance', bypass_manifest, sandbox_generated=True)
    controls.persist_snapshots(bypass_results, destination / 'mutations/gate_bypass')
    evaluated = evaluate(bypass_results[0], destination / 'public_inputs/fixtures/scenarios/missing_file', plan, 'missing_file', schemas)
    mutations['gate_bypass'] = {'detected': not evaluated['pass'], 'evaluation': evaluated}
    return {'scenarios': outcomes, 'negative_controls': mutations, 'source_sha256': controls.sha256(source),
            'control_pass': len(outcomes) == len(policy['scenarios']) and all(x['pass'] for x in outcomes.values())
                            and all(x['detected'] for x in mutations.values()),
            'scope': 'New complete local mechanism-control workflow, not the original corpus pipeline'}


def render(run):
    lines = ['# V2 complete local workflow-family controls', '',
             f"Package {run['package_version']}; audit protocol {run['audit_protocol_version']}; state {run['status']}; LLM calls 0.", '',
             'New file → CSV validation → CSV export controls. Not original-corpus G6-Assert scores.', '',
             '| Fixture source | Scenario checks passed | Negative controls detected | Control pass |', '|---|---:|---:|---|']
    for key, record in run['results'].items():
        lines.append(f"| {key} | {sum(v['pass'] for v in record.get('scenarios', {}).values())}/5 | {sum(v['detected'] for v in record.get('negative_controls', {}).values())}/3 | {record.get('control_pass', False)} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', type=Path)
    args = parser.parse_args(argv)
    policy = replay.read_json(CONFIG)
    if (policy['scenarios'] != ['nominal', 'extra_row', 'changed_value', 'missing_file', 'missing_column']
            or policy['negative_controls'] != ['constant_export', 'corrupt_export_value', 'gate_bypass']):
        raise ValueError('Control definitions changed; use a separate versioned protocol')
    previous_root = ROOT / policy['parent_replay']
    previous = replay.read_json(previous_root / 'run.json')
    if previous['status'] != 'complete' or not previous['source_inputs_unchanged'] or previous['environment'] != controls.environment():
        raise ValueError('Completed unchanged replay in the same environment is required')
    hashes = parent.verify_hashes(previous_root, previous)
    original_inventory = replay.read_json(Path(previous['inventory_directory']) / 'run.json')
    baseline = Path(original_inventory['control_directory'])
    sources = [(item, baseline / 'cases' / item['case'] / 'public_workspace' / item['case'] / item['path']) for item in policy['fixture_sources']]
    if args.dry_run:
        print(json.dumps({'package_version': policy['package_version'], 'fixture_sources': len(sources),
                          'scenario_checks': len(sources) * 5, 'negative_controls': len(sources) * 3,
                          'llm_calls': 0, 'original_corpus_scores': False}, indent=2))
        return 0
    paths = list(dict.fromkeys([*FILES, previous_root / 'run.json', previous_root / 'input_sha256.json',
                               *[p for _, p in sources]]))
    hashes.update({str(p.resolve()): controls.sha256(p) for p in paths})
    fingerprint = controls.fingerprint(hashes)
    if args.resume:
        output = args.resume.resolve()
        run = replay.read_json(output / 'run.json')
        if run['input_fingerprint'] != fingerprint:
            raise ValueError('Family implementation or inputs changed; start a separate condition')
    else:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        output = ROOT / 'audit/outputs' / f'package_v2_family__{stamp}__{uuid.uuid4().hex[:8]}'
        output.mkdir(parents=True, exist_ok=False)
        run = {'package_version': policy['package_version'], 'audit_protocol_version': policy['audit_protocol_version'],
               'input_fingerprint': fingerprint, 'environment': controls.environment(), 'llm_calls': 0, 'results': {}}
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
        raise ValueError('Family verification failed; inspect verification.txt')
    for item, source in sources:
        identity = item['case'] + '/' + Path(item['path']).name
        if identity in run['results']:
            continue
        destination = output / 'controls' / item['case'] / Path(item['path']).stem / ('attempt_' + uuid.uuid4().hex[:8])
        try:
            record = run_source(source, destination, policy)
        except Exception as exc:
            record = {'control_pass': False, 'error': f'{type(exc).__name__}: {exc}'}
        record['artifact_directory'] = str(destination)
        run['results'][identity] = record
        controls.write_json(destination / 'result.json', record)
        controls.write_json(output / 'run.json', run)
        (output / 'summary.md').write_text(render(run))
        print(f"{identity}: control_pass={record['control_pass']}", flush=True)
    try:
        parent.verify_hashes(output, run)
        unchanged = True
    except ValueError as exc:
        unchanged = False
        run['integrity_error'] = str(exc)
    run['source_inputs_unchanged'] = unchanged
    run['status'] = ('inputs_changed' if not unchanged else 'complete' if all(r['control_pass'] for r in run['results'].values()) else 'complete_with_failures')
    controls.write_json(output / 'run.json', run)
    (output / 'summary.md').write_text(render(run))
    print(f"{run['status']}: {output / 'summary.md'}", flush=True)
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
