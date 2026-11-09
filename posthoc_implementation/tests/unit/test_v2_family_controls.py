"""Workflow dataflow, gate, semantic-negative, and actual prompt rendering tests."""
import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_v2_family_controls as family


def public_input(tmp_path):
    fixtures = tmp_path / 'fixtures'
    fixtures.mkdir()
    (fixtures / 'source.csv').write_text('name,value\na,7\nb,11\n')
    (fixtures / 'location.json').write_text('{"driver":"fixture-filesystem","root":"."}')
    return fixtures


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_full_dataflow_uses_actual_producer_output(tmp_path):
    fixtures = public_input(tmp_path)
    plan = family.make_plan(['name', 'value'])
    result = family.engine.execute(plan, tmp_path / 'work', fixtures)
    assert result['states'] == {'detect': 'executed', 'validate': 'executed', 'export': 'executed'}
    observed = {'_snapshot': snapshot(tmp_path / 'work'), '_errors': []}
    assert family.evaluate(observed, fixtures, plan, 'nominal', family.public_schemas())['pass']
    assert (tmp_path / 'work/artifacts/exported.csv').read_text() == 'name,value\na,7\nb,11\n'


def test_task_order_derived_from_dependencies_not_list_order(tmp_path):
    plan = family.make_plan(['name', 'value'])
    plan['bindings'].reverse()
    assert family.engine.compile_plan(plan) == ['detect', 'validate', 'export']


def test_missing_file_is_a_true_gate_skip_not_a_loader_error(tmp_path):
    fixtures = public_input(tmp_path)
    (fixtures / 'source.csv').unlink()
    plan = family.make_plan(['name', 'value'])
    result = family.engine.execute(plan, tmp_path / 'work', fixtures)
    assert result['workflow_status'] == 'completed'
    assert result['states'] == {'detect': 'executed', 'validate': 'skipped', 'export': 'skipped'}
    assert family.evaluate({'_snapshot': snapshot(tmp_path / 'work'), '_errors': []}, fixtures, plan, 'missing_file')['pass']


def test_missing_columns_fail_before_export(tmp_path):
    fixtures = public_input(tmp_path)
    (fixtures / 'source.csv').write_text('name\na\n')
    plan = family.make_plan(['name', 'value'])
    result = family.engine.execute(plan, tmp_path / 'work', fixtures)
    assert result['states']['validate'] == 'failed' and result['states']['export'] == 'skipped'
    assert family.evaluate({'_snapshot': snapshot(tmp_path / 'work'), '_errors': ['expected validation rejection']},
                           fixtures, plan, 'missing_column')['pass']


@pytest.mark.parametrize('change', ['cycle', 'unknown_service', 'unknown_edge_predicate', 'unknown_field', 'missing_external_binding'])
def test_unimplemented_or_invalid_workflow_rejected_before_writes(change):
    plan = family.make_plan(['name', 'value'])
    if change == 'cycle':
        plan['edges'].append({'from': 'export', 'to': 'validate'})
    elif change == 'unknown_service':
        plan['bindings'][2]['service_id'] = 'unimplemented_service'
    elif change == 'unknown_edge_predicate':
        plan['edges'][0]['when'] = 'anything'
    elif change == 'unknown_field':
        plan['arbitrary_branch'] = True
    else:
        plan['artifacts'][0].pop('fixture_ref')
    with pytest.raises(ValueError):
        family.engine.compile_plan(plan)


def test_wrong_upstream_artifact_is_not_substituted(tmp_path):
    fixtures = public_input(tmp_path)
    plan = family.make_plan(['name', 'value'])
    plan['bindings'][2]['input_bindings'][0]['artifact_id'] = 'metadata'
    result = family.engine.execute(plan, tmp_path / 'work', fixtures)
    assert result['states']['export'] == 'failed'
    assert 'exported.csv' not in str(snapshot(tmp_path / 'work'))


@pytest.mark.parametrize('mode', ['constant', 'wrong_value', 'wrong_count'])
def test_semantic_oracle_detects_plausible_bad_outputs(tmp_path, mode):
    fixtures = public_input(tmp_path)
    plan = family.make_plan(['name', 'value'])
    family.engine.execute(plan, tmp_path / 'work', fixtures)
    data = snapshot(tmp_path / 'work')
    if mode == 'constant':
        data['artifacts/exported.csv'] = b'name,value\n'
    elif mode == 'wrong_value':
        data['artifacts/exported.csv'] = b'name,value\na,700\nb,11\n'
    else:
        status = json.loads(data['artifacts/export_status.json'])
        status['rows_written'] = 999
        data['artifacts/export_status.json'] = json.dumps(status).encode()
    assert not family.evaluate({'_snapshot': data, '_errors': []}, fixtures, plan, 'nominal')['pass']


def test_gate_bypass_detected_as_wrong_behavior(tmp_path):
    fixtures = public_input(tmp_path)
    (fixtures / 'source.csv').unlink()
    plan = family.make_plan(['name', 'value'])
    plan['gates'] = []
    family.engine.execute(plan, tmp_path / 'work', fixtures)
    assert not family.evaluate({'_snapshot': snapshot(tmp_path / 'work'), '_errors': ['loader attempted']},
                               fixtures, plan, 'missing_file')['pass']


def workspace(tmp_path):
    fixtures = tmp_path / 'fixtures/inputs'
    fixtures.mkdir(parents=True)
    (fixtures / 'example.csv').write_text('name,value\npublic_marker,7\n')
    return tmp_path


def test_actual_m3_and_m4_prompts_contain_public_fixture_data(tmp_path):
    root = workspace(tmp_path)
    view = {'task': 'A public requirement', 'candidates': '{}', 'catalog': '{}',
            'serviceflow_schema': '{}', 'contracts': '{}'}
    manifest = {'catalog': {'version': 'x', 'sanitized_catalog_yaml_sha256': 'a'*64},
                'instance': {'benchmark_id': 'main:example', 'split': 'main', 'id': 'example'},
                'task': {'description_sha256': 'b'*64}}
    _, user = family.prompt_context.m3_ir_prompts(view, manifest, workspace=root)
    assert 'public_marker,7' in user and 'fixtures/inputs/example.csv' in user
    assert 'artifact.fixture_ref' in user
    diagnostics = {'gates': [], 'first_failing_gate': None}
    _, repaired = family.prompt_context.m4_repair_prompts(view, {'serviceflow.yaml': '{}'}, diagnostics, workspace=root)
    assert 'public_marker,7' in repaired and '# V2 public execution inputs' in repaired


def test_public_context_limit_fails_instead_of_silently_truncating(tmp_path):
    root = workspace(tmp_path)
    with pytest.raises(ValueError, match='declared limit'):
        family.prompt_context.render_context(root, max_bytes=1)


def test_complete_sandboxed_family_and_all_negative_controls(tmp_path):
    source = tmp_path / 'public.csv'
    source.write_text('name,value\na,7\nb,11\n')
    policy = family.replay.read_json(family.CONFIG)
    result = family.run_source(source, tmp_path / 'result', policy)
    assert result['control_pass'], result
    assert len(result['scenarios']) == 5
    assert all(v['detected'] for v in result['negative_controls'].values())
    preview = (tmp_path / 'result/generation_public_context.txt').read_text()
    assert '__changed' not in preview and 'missing_column' not in preview


def test_changed_values_not_only_counts_reach_downstream(tmp_path):
    fixtures = public_input(tmp_path)
    plan = family.make_plan(['name', 'value'])
    family.engine.execute(plan, tmp_path / 'first', fixtures)
    (fixtures / 'source.csv').write_text('name,value\na,19\nb,11\n')
    family.engine.execute(plan, tmp_path / 'second', fixtures)
    assert (tmp_path / 'first/artifacts/exported.csv').read_bytes() != (tmp_path / 'second/artifacts/exported.csv').read_bytes()
