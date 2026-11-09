"""Actual-controller integration, real stage computations and public/private split."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_method_experiment as runner

public, bridge = runner.public, runner.bridge
spec = importlib.util.spec_from_file_location('semantic_resolution_test_examples', ROOT / 'tests/unit/test_v2_semantic_resolution.py')
examples = importlib.util.module_from_spec(spec); spec.loader.exec_module(examples)


def profile(): return runner.replay.read_json(ROOT / 'audit/v2/runtime_profiles/bounded-window-1.json')


def synthetic_inputs(root):
    root.mkdir()
    config = {'inputs': {'readings': 'readings.jsonl', 'buildings': 'registry.csv'},
        'batch_window_start': '2026-01-01T00:00:00Z', 'batch_window_end': '2026-01-01T01:00:00Z',
        'window_size_minutes': 30, 'demand_threshold_pct': 85, 'power_factor_min': .85}
    (root / 'fixture.json').write_text(json.dumps(config))
    rows = [{'meter_id': 'm', 'building_id': 'b', 'timestamp': time, 'energy_kwh': energy,
             'demand_kw': demand, 'power_factor': quality}
            for time, energy, demand, quality in [('2026-01-01T00:00:00Z', 2.5, 40, .9),
              ('2026-01-01T00:15:00Z', 3.5, 85, .8), ('2026-01-01T00:30:00Z', 4, 30, .95)]]
    (root / 'readings.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    (root / 'registry.csv').write_text('building_id,demand_limit_kw\nb,100\n')
    return rows


@pytest.mark.parametrize('scenario', ['nominal', 'conflicting_duplicate', 'unknown_building', 'missing_energy'])
def test_generated_stage_scripts_are_self_contained_and_do_real_work(scenario, tmp_path):
    ir, _ = examples.complete(examples.synthetic_ir('fully_renamed'))
    fixtures = tmp_path / 'inputs'; rows = synthetic_inputs(fixtures)
    if scenario == 'conflicting_duplicate': rows.append({**rows[0], 'energy_kwh': 999})
    if scenario == 'unknown_building': rows[0]['building_id'] = 'absent'
    if scenario == 'missing_energy': del rows[0]['energy_kwh']
    (fixtures / 'readings.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    destination = tmp_path / 'execution'
    errors = []
    for intent in public.checked_plan(ir, profile())['order']:
        script = tmp_path / (intent + '.py')
        script.write_text(public.task_script(ir, profile(), intent))
        # Trusted compiler code and synthetic inputs only; no saved model code.
        executed = subprocess.run([sys.executable, '-I', str(script), '--workspace', str(destination), '--fixtures', str(fixtures)], capture_output=True, text=True)
        if executed.returncode:
            errors.append(executed.stderr); break
    snapshot = {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    result = {'scenario': scenario, '_snapshot': snapshot, '_errors': errors}
    design = {'positive_scenarios': ['nominal']}
    check = runner.prior.pilot.integration.evaluate(result, ir, fixtures, profile(), design)
    assert check['pass'], check
    assert runner.prior.pilot.integration.prior.real.oracle.check(result, ir, fixtures, profile(), scenario)['pass']
    if scenario == 'nominal':
        payload = json.loads(snapshot['artifacts/fully_renamed_bundle_6.json'])
        assert [r['energy_kwh_sum'] for r in payload['metrics']] == [6, 4]
        assert json.loads(snapshot['logs/semantic_backend_receipt.json'])['mock_fallback'] is False


def test_missing_control_edge_is_not_silently_added():
    ir, _ = examples.complete(examples.synthetic_ir())
    ir['control_flow']['edges'].pop()
    with pytest.raises(ValueError, match='Declare data dependencies'): public.checked_plan(ir, profile())


def public_workspace(tmp_path):
    # A retained model-generated development composition supplies a realistic
    # full-schema compiler control. No native reference graph or gold is read.
    source = ROOT / 'audit/outputs/controls__20261024T114039Z__9378fab4/cases/extension/building_energy_window_aggregation/public_workspace/extension/building_energy_window_aggregation'
    workspace = tmp_path / 'workspace'
    for name in ('task.md', 'candidates', 'catalog', 'contracts', 'schemas', 'fixtures', 'workspace.yaml', 'bin'):
        path = source / name
        if path.is_dir(): shutil.copytree(path, workspace / name)
        else:
            (workspace / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, workspace / name)
    ir = runner.replay.read_json(ROOT / 'audit/outputs/package_v2_semantic_resolution__20261025T231650Z__ae179ff4/execution_attempt/candidate_ir.json')
    contract = {'version': public.VERSION, 'metadata': {k: ir[k] for k in runner.generation.compact_ir.BOOKKEEPING},
                'profile': profile(), 'projection': examples.contract(), 'assembly_policy': examples.policy(),
                'rules': (ROOT / 'audit/v2/SEMANTIC_METHOD_CONTRACT.md').read_text()}
    runner.controls.write_json(workspace / public.CONTRACT, contract)
    return workspace, ir


def test_shared_real_compiler_preserves_graph_and_passes_public_static_gates(tmp_path):
    workspace, ir = public_workspace(tmp_path)
    submission = workspace / 'submission'; submission.mkdir()
    (submission / 'serviceflow.yaml').write_text(json.dumps(ir))
    public.compile_submission(workspace, submission)
    manifest = runner.controls.load(submission / 'runtime/manifest.yaml')
    assert len(manifest['tasks']) == len(ir['service_intents']) == 6
    assert public.original_submission._manifest_edges(manifest) == {(e['from'], e['to']) for e in ir['control_flow']['edges']}
    report = public.validate_submission(workspace, submission, run_execution=False)
    assert report['overall_status'] == 'pass', report
    assert report['gates'][-1]['status'] == 'skipped'
    assert runner.controls.load(submission / 'serviceflow.yaml') == ir
    # Argo must contain self-contained real scripts, not imports of host-only
    # modules or missing adjacent ir.json/profile.json files.
    argo_text = '\n'.join(p.read_text() for p in (submission / 'argo').glob('*.yaml'))
    assert 'execute_stage' in argo_text and 'schema_example' not in argo_text


def test_public_any_compatibility_does_not_hide_other_type_or_contract_errors():
    ir = examples.synthetic_ir()
    context = SimpleNamespace(serviceflow_valid=True, serviceflow=ir,
        load_catalog=lambda: {(b['service_id'], b['service_version']): examples.catalog_get(b['service_id'], b['service_version'])[0] for b in ir['bindings']})
    intent = ir['bindings'][0]['intent_id']
    diagnostics = [dict(code='G3_INPUT_TYPE_MISMATCH', message=f"{intent}: input 'input_artifacts' expects any, got json"),
        dict(code='G3_INPUT_TYPE_MISMATCH', message=f"{intent}: input 'input_artifacts' expects any, got table"),
        dict(code='G3_REQUIRED_OUTPUT_UNBOUND', message='Required execution report absent')]
    assert public.compatible_any_diagnostics(context, diagnostics) == diagnostics[1:]


class FakeClient:
    def __init__(self, responses): self.responses = iter(responses); self.calls = []
    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=next(self.responses))


def test_actual_m3_generates_once_and_receives_no_validator_feedback(tmp_path):
    workspace, ir = public_workspace(tmp_path)
    module = bridge.method_module(workspace)
    module.validate_submission = lambda *args, **kwargs: pytest.fail('M3 must not request feedback')
    client = FakeClient([json.dumps(ir)])
    original_materializer = bridge.original_methods.materialize_runtime
    result = module.run_m3(client, workspace, workspace / 'submission')
    assert result.status == 'completed' and result.error is None
    assert len(client.calls) == 1 and result.validator_calls == 0
    assert bridge.original_methods.materialize_runtime is original_materializer
    prompt = client.calls[0]['system'] + client.calls[0]['user']
    assert 'deterministic mocks' not in prompt and 'mock scripts' not in prompt
    assert 'prompt2serviceflow_extension_sources' in prompt
    assert 'conflicting_duplicate' not in prompt and 'boundary_records' not in prompt


def test_actual_m4_uses_its_parse_repair_loop_with_shared_contract_only(tmp_path):
    workspace, ir = public_workspace(tmp_path)
    module = bridge.method_module(workspace)
    module.validate_submission = lambda *args, **kwargs: {'overall_status': 'pass', 'first_failing_gate': None,
        'gates': [{'gate': name, 'status': 'pass', 'diagnostics': []} for name in module.GATE_ORDER]}
    client = FakeClient(['malformed: [', json.dumps(ir)])
    result = module.run_m4(client, workspace, workspace / 'submission', repair_budget=3)
    assert result.status == 'completed' and result.validator_calls == 1
    assert [c['stage'] for c in client.calls] == ['m3_ir', 'm4_repair_parse']
    assert result.attempts[0]['synthetic'] is True
    assert all('Shared v2 public execution contract' in c['user'] for c in client.calls)
    assert all('conflicting_duplicate' not in c['user'] for c in client.calls)


def test_actual_pi_staging_preserves_budget_shim_and_excludes_evaluators(tmp_path):
    workspace, _ = public_workspace(tmp_path)
    module = bridge.agent_module()
    staged = module.stage_agent_workspace(workspace, tmp_path / 'agent', validator_budget=4)
    assert '.validate_submission_real' in (staged / 'bin/validate_submission').read_text()
    assert 'COUNT -gt 4' in (staged / 'bin/validate_submission').read_text()
    assert 'semantic_public_tools' in (staged / 'bin/.validate_submission_real').read_text()
    method = (staged / 'METHOD.md').read_text()
    assert 'v2_contract.json' in method and 'zenodo_pipeline_descriptions' not in method
    assert 'conflicting_duplicate' not in method
    context = tmp_path / 'image'
    module.prepare_image_context(context)
    assert {p.stem for p in (context / 'v2').glob('*.py')} == set(public.PUBLIC_MODULES)
    assert not any('oracle' in p.name or p.name == 'evaluation_fixtures' for p in context.rglob('*'))
    assert 'pi-coding-agent@0.82.0' in (context / 'Dockerfile').read_text()


def test_pi_proxy_forwards_standard_messages_reasoning_and_tools_with_shared_decoding(tmp_path, monkeypatch):
    module = bridge.agent_module()
    module.prepare_proxy_context(tmp_path)
    spec = importlib.util.spec_from_file_location('v2_proxy_under_test', tmp_path / 'proxy.py')
    proxy = importlib.util.module_from_spec(spec); spec.loader.exec_module(proxy)
    request = {'model': 'unit', 'messages': [{'role': 'assistant', 'content': '', 'reasoning_content': 'retain',
        'tool_calls': [{'id': 'one', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'one', 'content': 'public data'}]}
    response = {'choices': [{'message': {'role': 'assistant', 'content': 'visible', 'reasoning_content': 'internal',
        'tool_calls': [{'id': 'two', 'type': 'function', 'function': {'name': 'write', 'arguments': '{}'}}]}}],
        'usage': {'prompt_tokens': 5, 'completion_tokens': 7, 'total_tokens': 12}}
    raw_response = json.dumps(response).encode()
    capture, logs = {}, []
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, method, path, body, headers): capture['request'] = json.loads(body)
        def getresponse(self): return SimpleNamespace(read=lambda: raw_response, status=200, getheader=lambda *args: 'application/json')
        def close(self): pass
    monkeypatch.setattr(proxy.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(proxy.http.client, 'HTTPConnection', Connection)
    monkeypatch.setattr(proxy, 'UPSTREAM_API_KEY', 'test-secret-token')
    monkeypatch.setattr(proxy, 'MAX_TOTAL_TOKENS', 0)
    monkeypatch.setattr(proxy, '_log', logs.append)
    monkeypatch.setenv('P2SF_DECODING', json.dumps({'temperature': .2, 'top_p': 1, 'seed': 202, 'max_tokens': 16384}))
    handler = proxy.Handler.__new__(proxy.Handler)
    body = json.dumps(request).encode()
    handler.rfile = io.BytesIO(body)
    handler.path = '/v1/chat/completions'
    handler.headers = {'Content-Length': str(len(body))}
    handler._respond = lambda status, payload, kind: capture.update(status=status, payload=payload)
    handler.do_POST()
    assert capture['request']['messages'] == request['messages']
    assert capture['request']['seed'] == 202 and capture['request']['temperature'] == .2
    assert capture['payload'] == raw_response
    assert any(e['event'] == 'response_wire' and 'reasoning_content' in e['body'] for e in logs)
    assert 'test-secret-token' not in json.dumps(logs)


def test_recording_client_never_promotes_reasoning_to_final(tmp_path, monkeypatch):
    model = runner.ModelConfig('unit', 'unit', 'http://localhost/v1', 'UNIT_TOKEN', top_p=1, seed=101)
    ledger = runner.UsageLedger()
    monkeypatch.setenv('UNIT_TOKEN', 'unit-token')
    monkeypatch.setattr(runner.generation.transport, 'complete', lambda *args: {
        'status': 'response_received', 'latency_s': .01, 'response': {'model': 'unit',
            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '', 'reasoning_content': '{"not":"an answer"}'}}],
            'usage': {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5}}})
    result = runner.RecordingClient(model, ledger, tmp_path).complete(stage='m3_ir', system='public', user='task')
    assert result.text == '' and ledger.calls == 1 and ledger.total_tokens == 5
    assert 'reasoning_content' in (tmp_path / '001_m3_ir/response.json').read_text()


def install_batch(tmp_path, monkeypatch, control_pass=True):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    design = {'case': 'extension/unit', 'models': ['unit'], 'pilot_model': 'unit', 'methods': ['m3', 'm4', 'm5'],
              'seeds': [101, 202, 303], 'pilot_seed': 101, 'package_version': 'unit', 'audit_protocol_version': 'unit'}
    prepared = {'design': design, 'hashes': {}, 'freeze': {'freeze_id': 'unit'},
                'models': {'unit': runner.ModelConfig('unit', 'unit', 'http://localhost/v1', 'UNIT_TOKEN')}}
    monkeypatch.setattr(runner, 'prepare', lambda: copy.deepcopy(prepared))
    monkeypatch.setenv('UNIT_TOKEN', 'not-a-live-token')
    monkeypatch.setattr(runner.controls, 'environment', lambda: {'unit_environment': True})
    monkeypatch.setattr(runner.bridge, 'agent_module', lambda: SimpleNamespace(inspect_image_digests=lambda: {'agent': 'unit', 'proxy': 'unit'}))
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='verification', stderr=''))
    def control(p, directory):
        directory.mkdir()
        value = {'control_gate_pass': control_pass, 'negative_controls': {}, 'public_overall': 'pass' if control_pass else 'fail'}
        runner.controls.write_json(directory / 'result.json', value)
        return value
    monkeypatch.setattr(runner, 'integration_controls', control)
    calls = []
    def execute(p, model, method, seed, directory, skip_images):
        calls.append((model, method, seed))
        directory.mkdir(parents=True)
        result = {'model': model, 'method': method, 'seed': seed, 'case': design['case'], 'validity': 'valid',
                  'usage': {}, 'evaluation': {'state': 'evaluated', 'evaluated': True, 'business_pass': False}}
        runner.controls.write_json(directory / 'result.json', result)
        return result
    monkeypatch.setattr(runner, 'execute_cell', execute)
    return calls


def test_failed_real_integration_control_stops_before_any_paid_cell(tmp_path, monkeypatch):
    calls = install_batch(tmp_path, monkeypatch, False)
    assert runner.main([]) == 1
    assert calls == []
    output = next((tmp_path / 'audit/outputs').iterdir())
    assert runner.replay.read_json(output / 'run.json')['status'] == 'control_gate_failed_no_inference'


def test_controls_only_never_needs_a_token_or_inference(tmp_path, monkeypatch):
    calls = install_batch(tmp_path, monkeypatch)
    monkeypatch.delenv('UNIT_TOKEN')
    assert runner.main(['--controls-only']) == 0
    assert calls == []


def test_resume_preserves_completed_semantic_failures_without_resampling(tmp_path, monkeypatch):
    calls = install_batch(tmp_path, monkeypatch)
    assert runner.main([]) == 0
    output = next((tmp_path / 'audit/outputs').iterdir())
    assert len(calls) == 3
    assert runner.main(['--resume', str(output)]) == 0
    assert len(calls) == 3
    assert len(runner.replay.read_json(output / 'results.json')) == 3


@pytest.mark.parametrize('has_result', [False, True])
def test_crash_before_checkpoint_does_not_repeat_a_paid_attempt(has_result, tmp_path, monkeypatch):
    calls = install_batch(tmp_path, monkeypatch)
    runner.main([])
    output = next((tmp_path / 'audit/outputs').iterdir())
    record = runner.replay.read_json(output / 'run.json')
    key = 'unit/m3/101'
    saved = record['result_files'].pop(key)
    runner.controls.write_json(output / 'run.json', record)
    if not has_result: Path(saved['path']).unlink()
    assert runner.main(['--resume', str(output)]) == 0
    assert len(calls) == 3
    row = runner.replay.read_json(Path(saved['path']))
    assert row['validity'] == ('valid' if has_result else 'invalid_interrupted_attempt')


def test_changed_completed_cell_blocks_resume(tmp_path, monkeypatch):
    install_batch(tmp_path, monkeypatch)
    runner.main([])
    output = next((tmp_path / 'audit/outputs').iterdir())
    saved = runner.replay.read_json(output / 'run.json')['result_files']['unit/m3/101']
    Path(saved['path']).write_text('{}')
    with pytest.raises(ValueError): runner.main(['--resume', str(output)])
