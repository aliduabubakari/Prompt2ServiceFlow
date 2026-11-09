"""Public contract parity, failing-IR diagnostics and deployed-tool isolation."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_fusion_v2_3 as runner

spec = importlib.util.spec_from_file_location('relational_v23_examples', ROOT / 'tests/unit/test_v2_fusion.py')
examples = importlib.util.module_from_spec(spec); spec.loader.exec_module(examples)


def workspace_at(tmp_path):
    workspace, value = examples.public_workspace(tmp_path)
    contract = json.loads((workspace / 'v2_contract.json').read_text())
    contract['version'] = runner.public.VERSION
    contract['execution_input_constraints'] = runner.public.input_constraints()
    overlay, index = runner.inputs.catalog_overlay(workspace, contract['execution_input_constraints'])
    for name, data in overlay.items(): (workspace / name).write_bytes(data)
    snapshot = contract['metadata']['catalog_snapshot']
    snapshot['version'], snapshot['sha256'] = index['version'], runner.inputs.sha(overlay['catalog/catalog.yaml'])
    value['catalog_snapshot'] = copy.deepcopy(snapshot)
    (workspace / 'v2_contract.json').write_text(json.dumps(contract))
    return workspace, value, contract


def test_missing_inputs_are_localized_without_repair_or_gate_reordering(tmp_path):
    workspace, value, _ = workspace_at(tmp_path)
    for b in value['bindings'][:3]: b['input_bindings'] = []
    for i in value['service_intents'][:3]: i['inputs'] = []
    original = copy.deepcopy(value)
    submission = workspace / 'submission'; submission.mkdir()
    path = submission / 'serviceflow.yaml'; path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(ValueError, match=r'\$\.bindings\[0\].input_bindings:.*expected exactly 1.*got 0'):
        runner.public.compile_submission(workspace, submission)
    report = runner.public.validate_submission(workspace, submission, run_execution=False)
    assert report['overall_status'] == 'fail' and report['first_failing_gate'] == 'G0'
    g0, g3 = report['gates'][0], next(g for g in report['gates'] if g['gate'] == 'G3')
    missing = next(d for d in g0['diagnostics'] if d.get('path') == 'submission/runtime/manifest.yaml')
    assert '$.bindings[0].input_bindings' in missing['message']
    assert 'do not edit derived runtime' in missing['message']
    causes = [d for d in g3['diagnostics'] if d['code'] == 'V2_INPUT_BINDING_CONTRACT']
    assert [d['path'] for d in causes] == [f'$.bindings[{i}].input_bindings' for i in range(3)]
    assert all(d['expected_count'] == 1 and d['actual_count'] == 0 for d in causes)
    assert path.read_bytes() == before and value == original
    assert not (submission / 'runtime/manifest.yaml').exists()


@pytest.mark.parametrize('defect', ['too_many', 'duplicate', 'wrong_port'])
def test_input_feedback_retains_strict_cardinality_and_ports(defect):
    value = examples.ir(); b = value['bindings'][3]
    if defect == 'too_many': b['input_bindings'].append(copy.deepcopy(b['input_bindings'][0]))
    elif defect == 'duplicate': b['input_bindings'][1] = copy.deepcopy(b['input_bindings'][0])
    else: b['input_bindings'][0]['port'] = 'unknown'
    before = copy.deepcopy(value)
    assert runner.public.input_diagnostics(value)[0]['expected_count'] == 3
    with pytest.raises(ValueError): runner.public.checked_plan(value, examples.profile())
    assert value == before


def test_schema_and_unrelated_contract_failures_remain_failures(tmp_path):
    workspace, value, _ = workspace_at(tmp_path)
    value['requirement']['topology'] = 'fan_in'
    submission = workspace / 'submission'; submission.mkdir()
    (submission / 'serviceflow.yaml').write_text(json.dumps(value))
    report = runner.public.validate_submission(workspace, submission, run_execution=False)
    assert report['first_failing_gate'] == 'G0'
    assert any(d['code'] == 'G0_SCHEMA_ERROR' for d in report['gates'][0]['diagnostics'])
    value = examples.ir(); value['bindings'][0]['parameter_bindings']['operation_profile'] = 'invented'
    assert runner.public.input_diagnostics(value) == []
    with pytest.raises(ValueError, match='Unregistered operation'): runner.public.checked_plan(value, examples.profile())


def test_public_bundle_roundtrips_allowlisted_information_and_fits_reads(tmp_path):
    workspace, _, contract = workspace_at(tmp_path)
    # Files outside the fixed allowlist must never enter the generated bundle.
    (workspace / 'private_reference_ir.json').write_text('{"private_marker":"SECRET_EVALUATOR_VALUE"}')
    sizes = runner.inputs.write_bundles(workspace, contract)
    assert all(r['bytes'] < runner.inputs.MAX_BUNDLE_BYTES for r in sizes.values())
    core = json.loads((workspace / runner.inputs.CONTEXT).read_text())
    interfaces = json.loads((workspace / runner.inputs.INTERFACES).read_text())
    assert core['task'] == (workspace / 'task.md').read_text()
    assert core['execution_contract'] == contract
    expected = {s for row in core['candidates']['candidate_sets'] for s in row['service_ids']}
    assert {d['service_id'] for d in interfaces['candidate_descriptors']} == expected
    for descriptor in interfaces['candidate_descriptors']:
        assert descriptor == runner.controls.load(workspace / 'catalog/services' / (descriptor['service_id'] + '.yaml'))
    assert interfaces['serviceflow_schema'] == json.loads((workspace / 'schemas/serviceflow_ir.schema.json').read_text())
    assert 'SECRET_EVALUATOR_VALUE' not in ''.join((workspace / name).read_text() for name in sizes)
    catalog = runner.controls.load(workspace / 'catalog/catalog.yaml')
    for row in catalog['services']:
        if row['service_id'] in runner.public.backend.OPERATIONS:
            assert row['sha256'] == runner.controls.sha256(workspace / 'catalog' / row['descriptor_path'])
            descriptor = runner.controls.load(workspace / 'catalog' / row['descriptor_path'])
            port = descriptor['interface']['inputs'][0]
            rule = runner.public.input_constraints()[row['service_id']]
            assert port['required'] is True and port['cardinality'] == ('many' if rule['minimum'] == 3 else 'one')


def test_shared_method_information_and_m5_budget_are_preserved(tmp_path):
    workspace, value, contract = workspace_at(tmp_path)
    runner.inputs.write_bundles(workspace, contract)
    class Client:
        def complete(self, **kwargs):
            self.request = kwargs
            return type('Response', (), {'text': json.dumps(value)})()
    client = Client(); methods = runner.bridge.method_module(workspace)
    methods.run_m3(client, workspace, workspace / 'submission')
    assert contract['rules'] in client.request['user'] or 'Common compiler and validation rules' in client.request['user']
    assert 'execution_input_constraints' in client.request['user']
    agent = runner.agent_module()
    staged = agent.stage_agent_workspace(workspace, tmp_path / 'agent', validator_budget=4)
    assert 'Read `public_context.json`, then `public_interfaces.json` first' in (staged / 'METHOD.md').read_text()
    assert 'COUNT -gt 4' in (staged / 'bin/validate_submission').read_text()
    for name in (runner.inputs.CONTEXT, runner.inputs.INTERFACES):
        assert (staged / name).read_bytes() == (workspace / name).read_bytes()
    assert runner.previous.public.VERSION == 'p2sf.public-relational-methods/2'
    assert runner.public.VERSION == 'p2sf.public-relational-methods/3'


def test_new_deployment_imports_without_host_paths_or_evaluator(tmp_path):
    agent = runner.agent_module(); context = tmp_path / 'image'
    agent.prepare_image_context(context)
    sources = context / 'v2'
    assert not any('oracle' in p.name or 'controls' in p.name for p in sources.iterdir())
    code = ('import sys;sys.path.insert(0,sys.argv[2]);sys.path.insert(0,sys.argv[1]);'
            'import semantic_public_tools as p;assert p.VERSION=="p2sf.public-relational-methods/3";'
            'assert "expected exactly" in p.backend_source(p.deployment_sources()["fusion_backend"]);'
            'assert p.input_constraints()["api_table_primary_source_ingestor"]["minimum"]==1')
    result = subprocess.run([sys.executable, '-c', code, str(sources), str(context / 'pkg/src')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert agent.M5_VERSION == 'v2.28.3'


def test_production_public_execution_still_passes_without_weaker_checks(tmp_path):
    workspace, value, _ = workspace_at(tmp_path)
    import shutil
    nominal = workspace / 'fixtures/scenarios/nominal'
    shutil.rmtree(nominal); examples.fixtures(nominal, examples.profile())
    submission = workspace / 'submission'; submission.mkdir()
    (submission / 'serviceflow.yaml').write_text(json.dumps(value))
    runner.public.compile_submission(workspace, submission)
    report = runner.public.validate_submission(workspace, submission)
    assert all(g['status'] == 'pass' for g in report['gates']), report
    assert runner.public.ops.publish.__code__.co_code == runner.previous.public.ops.publish.__code__.co_code
