"""Independent relational controls, real scripts, fan-in and frozen isolation."""
import copy
import csv
import hashlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_fusion_experiment as runner
import fusion_stage_runtime as stage


def profile(): return runner.replay.read_json(ROOT / 'audit/v2/runtime_profiles/relational-routing-1.json')


def task():
    return '\n'.join(f'{i}. {op[0]} - Public operation' for i, op in enumerate(runner.public.backend.OPERATIONS.values(), 1))


def ir(): return runner.fusion_controls.reference_ir({}, task())


def fixtures(root, p):
    root.mkdir(parents=True)
    f = p['fields']
    tickets = [{f['record_id']: 'record_a', f['join_key']: 'entity_1', f['priority']: ' High ', f['category']: 'billing', 'subject': 'First'},
               {f['record_id']: 'record_b', f['join_key']: 'entity_1', f['priority']: 'low', f['category']: 'security', 'subject': 'Second'},
               {f['record_id']: 'record_c', f['join_key']: 'entity_2', f['priority']: 'medium', f['category']: 'technical', 'subject': 'Third'}]
    lookup = [{f['join_key']: 'entity_1', f['tier']: 'enterprise', f['churn']: 'low', f['numeric_lookup_fields'][0]: '100.5'},
              {f['join_key']: 'entity_2', f['tier']: 'starter', f['churn']: 'HIGH', f['numeric_lookup_fields'][0]: '10.25'}]
    policy = {'priority_weights': {'low': 1, 'medium': 2, 'high': 5}, 'tier_multipliers': {'enterprise': 2, 'starter': 1},
              'escalation_threshold': 10, 'churn_high_priority_threshold': 'medium', 'categories_requiring_immediate': ['security']}
    (root / 'events.json').write_text(json.dumps(tickets))
    (root / 'policy.json').write_text(json.dumps(policy))
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(lookup[0])); writer.writeheader(); writer.writerows(lookup)
    (root / 'lookup.csv').write_text(stream.getvalue())
    (root / 'fixture.json').write_text(json.dumps({'inputs': {p['inputs']['primary']: 'events.json', p['inputs']['secondary']: 'lookup.csv', p['inputs']['reference']: 'policy.json'}}))


def snapshot(root, scenario, errors):
    return {'scenario': scenario, '_errors': errors, '_snapshot': {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}}


def execute(value, p, inputs, root, scenario='nominal', scripts=False):
    plan = runner.public.checked_plan(value, p)
    errors = []
    for intent in plan['order']:
        if scripts:
            script = root.parent / (intent + '.py'); script.write_text(runner.public.task_script(value, p, intent))
            result = subprocess.run([sys.executable, '-I', str(script), '--workspace', str(root), '--fixtures', str(inputs)], capture_output=True, text=True)
            good = result.returncode == 0
        else: good = stage.execute_stage(value, p, intent, root, inputs)
        if not good: errors.append('expected rejecting stage'); break
    return snapshot(root, scenario, errors)


def test_join_routes_actual_values_and_consistent_mutants_are_detected(tmp_path):
    p, value = profile(), ir(); inputs = tmp_path / 'inputs'; fixtures(inputs, p)
    result = execute(value, p, inputs, tmp_path / 'execution', scripts=True)
    checked = runner.oracle.check(result, value, inputs, p, {})
    assert checked['pass'], checked
    payload = json.loads(result['_snapshot']['artifacts/' + runner.oracle.primary(value) + '.json'])
    assert [row['routing_score'] for row in payload['records']] == [10, 2, 2]
    assert all(row['escalation_required'] for row in payload['records'])
    for defect in ('empty_records', 'wrong_join', 'wrong_score', 'wrong_escalation'):
        bad = runner.oracle.check(runner.oracle.mutate(result, value, p, defect), value, inputs, p, {})
        assert not bad['pass']
        assert any(c['check'] == 'joined_records_and_routing_from_public_sources' and c['pass'] is False for c in bad['checks'])


def test_runtime_is_independent_of_case_artifact_and_field_names(tmp_path):
    p, value = profile(), ir()
    p['inputs'] = {'primary': 'p', 'secondary': 's', 'reference': 'r'}
    p['fields'] = {'record_id': 'row', 'join_key': 'entity', 'priority': 'urgency', 'category': 'kind', 'tier': 'class', 'churn': 'risk', 'numeric_lookup_fields': ['amount']}
    mapping = {a['artifact_id']: 'different_' + a['artifact_id'] for a in value['artifacts']}
    intents = {i['intent_id']: 'different_' + i['intent_id'] for i in value['service_intents']}
    for a in value['artifacts']:
        a['artifact_id'] = mapping[a['artifact_id']]
        if a['producer']: a['producer'] = intents[a['producer']]
        a['consumers'] = [intents[i] for i in a['consumers']]
    for i in value['service_intents']:
        i['intent_id'] = intents[i['intent_id']]
        for k in ('inputs', 'outputs'): i[k] = [mapping[a] for a in i[k]]
    for b in value['bindings']:
        b['intent_id'] = intents[b['intent_id']]
        for field in ('input_bindings', 'output_bindings'):
            for row in b[field]: row['artifact_id'] = mapping[row['artifact_id']]
    for edge in value['control_flow']['edges']:
        edge['from'], edge['to'] = intents[edge['from']], intents[edge['to']]
    value['control_flow']['parallel_groups'][0]['intent_ids'] = [intents[i] for i in value['control_flow']['parallel_groups'][0]['intent_ids']]
    inputs = tmp_path / 'inputs'; fixtures(inputs, p)
    result = execute(value, p, inputs, tmp_path / 'execution')
    assert runner.oracle.check(result, value, inputs, p, {})['pass']


def test_three_concurrent_ingestions_do_not_lose_fan_in_state(tmp_path):
    p, value = profile(), ir(); inputs = tmp_path / 'inputs'; fixtures(inputs, p)
    root = tmp_path / 'execution'
    plan = runner.public.checked_plan(value, p)
    first = [i for i in plan['order'] if not plan['parents'][i]]
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(lambda i: stage.execute_stage(value, p, i, root, inputs), first))
    for intent in plan['order']:
        if intent not in first: assert stage.execute_stage(value, p, intent, root, inputs)
    assert runner.oracle.check(snapshot(root, 'nominal', []), value, inputs, p, {})['pass']


def test_empty_business_input_is_valid_but_wrong_csv_header_is_not(tmp_path):
    p, value = profile(), ir(); inputs = tmp_path / 'inputs'; fixtures(inputs, p)
    (inputs / 'events.json').write_text('[]')
    result = execute(value, p, inputs, tmp_path / 'execution')
    assert runner.oracle.check(result, value, inputs, p, {})['pass']
    snap = result['_snapshot']
    payload = json.loads(snap['artifacts/' + runner.oracle.primary(value) + '.json'])
    bad = b'wrong_column\n'
    snap[payload['published_files']['csv']] = bad
    audit_path = payload['published_files']['audit']
    audit = json.loads(snap[audit_path]); audit['csv_sha256'] = hashlib.sha256(bad).hexdigest()
    snap[audit_path] = json.dumps(audit).encode()
    snap['artifacts/publication_audit.json'] = snap[audit_path]
    checked = runner.oracle.check(result, value, inputs, p, {})
    assert not checked['pass']
    assert any(c['check'] == 'published_csv_values' and not c['pass'] for c in checked['checks'])


def test_all_input_variants_and_specific_rejections_are_meaningful(tmp_path):
    p, value = profile(), ir(); nominal = tmp_path / 'public'; fixtures(nominal, p)
    design = runner.replay.read_json(runner.CONFIG)
    bank = tmp_path / 'bank'
    runner.fusion_controls.input_bank(nominal, bank, p, design)
    for original in nominal.iterdir(): assert original.read_bytes() == (bank / 'scenarios/nominal' / original.name).read_bytes()
    for scenario in design['positive_scenarios'] + design['rejection_scenarios']:
        inputs = bank / 'scenarios' / scenario
        result = execute(value, p, inputs, tmp_path / ('run_' + scenario), scenario)
        checked = runner.oracle.check(result, value, inputs, p, design['rejection_reasons'])
        assert checked['pass'], checked


@pytest.mark.parametrize('mutation', ['label', 'version', 'missing_status', 'missing_fan_in', 'status_payload', 'branch', 'hidden_edge', 'dependent_parallel'])
def test_unsupported_or_inconsistent_programs_are_not_repaired(mutation):
    value = ir()
    if mutation == 'label': value['bindings'][0]['parameter_bindings']['operation_profile'] = 'default'
    if mutation == 'version': value['bindings'][0]['service_version'] = '2.0.0'
    if mutation == 'missing_status':
        value['bindings'][0]['output_bindings'].pop()
        value['service_intents'][0]['outputs'].pop()
    if mutation == 'missing_fan_in': value['bindings'][3]['input_bindings'].pop()
    if mutation == 'status_payload':
        status = value['bindings'][0]['output_bindings'][1]['artifact_id']
        value['bindings'][3]['input_bindings'][0]['artifact_id'] = status
        value['service_intents'][3]['inputs'][0] = status
    if mutation == 'branch': value['control_flow']['branches'] = [{'unknown': True}]
    if mutation == 'hidden_edge': value['control_flow']['edges'].pop()
    if mutation == 'dependent_parallel': value['control_flow']['parallel_groups'][0]['intent_ids'].append('publish_outputs')
    original = copy.deepcopy(value)
    with pytest.raises((ValueError, KeyError)): runner.public.checked_plan(value, profile())
    assert value == original


def public_workspace(tmp_path):
    case = 'extension/support_profile_context_join'
    source = ROOT / 'audit/outputs/controls__20261024T114039Z__9378fab4/cases' / case / 'public_workspace' / case
    workspace = tmp_path / 'workspace'; workspace.mkdir()
    for name in ('task.md', 'candidates', 'catalog', 'contracts', 'schemas', 'fixtures', 'workspace.yaml', 'bin'):
        path = source / name
        if path.is_dir(): shutil.copytree(path, workspace / name)
        else: shutil.copy2(path, workspace / name)
    d = runner.replay.read_json(runner.CONFIG)
    metadata = runner.generation.public_metadata(workspace, runner.controls.load(workspace / 'workspace.yaml'), d)
    contract = {'version': runner.public.VERSION, 'metadata': metadata, 'profile': profile(), 'projection': runner.projection(),
        'assembly_policy': runner.replay.read_json(ROOT / 'audit/v2/assembly_policy.json'), 'rules': (ROOT / d['public_rules']).read_text()}
    runner.controls.write_json(workspace / 'v2_contract.json', contract)
    value = runner.fusion_controls.reference_ir(metadata, (workspace / 'task.md').read_text())
    return workspace, value


def test_full_public_schema_compilation_and_argo_graph_pass(tmp_path):
    workspace, value = public_workspace(tmp_path)
    submission = workspace / 'submission'; submission.mkdir()
    (submission / 'serviceflow.yaml').write_text(json.dumps(value))
    runner.public.compile_submission(workspace, submission)
    report = runner.public.validate_submission(workspace, submission, run_execution=False)
    assert report['overall_status'] == 'pass', report
    manifest = runner.controls.load(submission / 'runtime/manifest.yaml')
    assert len(manifest['tasks']) == 7
    assert runner.public.original_submission._manifest_edges(manifest) == {(e['from'], e['to']) for e in value['control_flow']['edges']}
    assert runner.controls.load(submission / 'serviceflow.yaml') == value


def test_actual_controllers_and_budget_shim_use_new_public_tools_without_touching_v27(tmp_path):
    workspace, value = public_workspace(tmp_path)
    old = runner.previous.public.VERSION
    class Client:
        def __init__(self): self.calls = []
        def complete(self, **kwargs):
            self.calls.append(kwargs)
            return type('Response', (), {'text': json.dumps(value)})()
    client = Client(); module = runner.bridge.method_module(workspace)
    result = module.run_m3(client, workspace, workspace / 'submission')
    assert result.status == 'completed' and result.error is None and len(client.calls) == 1
    assert 'relational-routing-1' in client.calls[0]['user'] and 'conflicting_duplicate' not in client.calls[0]['user']
    agent = runner.agent_module()
    assert agent.AGENT_IMAGE_TAG != runner.previous.bridge.agent_module().AGENT_IMAGE_TAG
    staged = agent.stage_agent_workspace(workspace, tmp_path / 'agent', validator_budget=4)
    assert 'COUNT -gt 4' in (staged / 'bin/validate_submission').read_text()
    context = tmp_path / 'image'; agent.prepare_image_context(context)
    assert (context / 'v2/semantic_public_tools_v27.py').is_file()
    assert not any('oracle' in p.name for p in (context / 'v2').glob('*'))
    # Import the actual vendor payload in an isolated process: no host audit
    # path may be needed by the public tools inside the image.
    script = 'import sys;sys.path.insert(0,sys.argv[2]);sys.path.insert(0,sys.argv[1]);import semantic_public_tools as p;assert p.VERSION=="p2sf.public-relational-methods/1";print(p.VERSION)'
    completed = subprocess.run([sys.executable, '-c', script, str(context / 'v2'), str(context / 'pkg/src')], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert runner.previous.public.VERSION == old == 'p2sf.public-real-methods/1'
