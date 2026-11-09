"""Static recognition must not execute code or turn private mappings into fixes."""
import copy
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_output_trace as pilot


def specs():
    return [{'artifact_id': 'report', 'data_type': 'status', 'media_type': None},
            {'artifact_id': 'json_report', 'data_type': 'json', 'json_value': {'success': True}},
            {'artifact_id': 'table', 'data_type': 'csv'}]


def plan(outputs=None, complete=True):
    return {'writers': [{**pilot.planned_output(o), 'intent_id': 'step'} for o in outputs or specs()],
            'complete_recognized_writer_plan': complete}


def definition(name='report'):
    return {'assertion_id': 'a', 'type': 'json_path_equals', 'path': 'artifacts/' + name + '.json', 'json_path': 'success'}


def check(): return {'status': 'fail', 'message': 'missing /tmp/artifacts/report.json'}


def ir():
    return {'artifacts': [{'artifact_id': o['artifact_id']} for o in specs()],
            'bindings': [{'intent_id': 'step', 'output_bindings': [{'port': 'execution_report', 'artifact_id': 'report'}]}]}


def test_only_the_frozen_renderer_ast_is_recognized():
    source = pilot.runtime_compiler._script_text(specs())
    assert pilot.recognize(source) == specs()
    assert pilot.recognize('# harmless comment\n' + source) == specs()
    assert pilot.recognize(source + '\nprint("extra behavior")\n') is None


def test_no_untrusted_expression_is_evaluated(tmp_path):
    target = tmp_path / 'never_created'
    source = f"OUTPUTS = __import__('pathlib').Path({str(target)!r}).write_text('bad')"
    assert pilot.recognize(source) is None
    assert not target.exists()


def test_mock_branch_predictions_match_actual_frozen_template_rules():
    assert pilot.planned_output(specs()[0])['path'] == 'artifacts/report.txt'
    assert pilot.planned_output(specs()[1])['path'] == 'artifacts/json_report.json'
    assert pilot.planned_output({'artifact_id': 'empty', 'data_type': 'json', 'json_value': {}})['kind'] == 'literal_json'
    assert pilot.planned_output({'artifact_id': 'zero', 'data_type': 'json', 'json_value': 0})['kind'] == 'literal_json'
    assert pilot.planned_output({'artifact_id': 'a', 'data_type': 'image'})['path'] == 'artifacts/a.bin'
    assert pilot.planned_output({'artifact_id': 'a', 'data_type': 'binary', 'media_type': 'application/pdf'})['path'] == 'artifacts/a.pdf'


def test_same_id_wrong_suffix_is_observed_without_renaming_anything():
    source = ir()
    old = copy.deepcopy(source)
    result = pilot.trace_predicate(definition(), check(), plan(), source, {})
    assert result['path_relation'] == 'same_artifact_id_different_suffix'
    assert result['same_id_planned_paths'] == ['artifacts/report.txt']
    assert source == old


def test_incomplete_writer_plan_does_not_claim_a_missing_path_is_explained():
    result = pilot.trace_predicate(definition(), check(), plan(complete=False), ir(), {})
    assert result['path_relation'] == 'unresolved_due_to_incomplete_writer_recognition'


def test_private_role_can_be_compared_but_no_alias_is_created():
    mappings = {'mappings': [{'intent_id': 'step', 'outputs': {'execution_report': 'expected_status'}}]}
    result = pilot.trace_predicate(definition('expected_status'), check(), plan(), ir(), mappings)
    assert result['path_relation'] == 'reference_role_bound_under_other_artifact_ids'
    assert result['model_role_bound_artifact_ids'] == ['report']
    assert 'alias' not in result and 'patch' not in result


def test_missing_literal_field_is_not_replaced_with_an_expected_value():
    d = definition('json_report')
    d['json_path'] = 'fixture.record_count'
    d['expected'] = 999
    result = pilot.trace_predicate(d, check(), plan(), ir(), {})
    assert result['literal_json_field_state'] == 'absent_or_incompatible'
    assert 'expected' not in result
    assert 'literal_json_field_value' not in result


def test_literal_field_value_is_inventoried_without_scoring_it():
    result = pilot.trace_predicate(definition('json_report'), check(), plan(), ir(), {})
    assert result['literal_json_field_state'] == 'present'
    assert result['literal_json_field_value'] is True
    assert 'new_status' not in result and 'semantic_success' not in result


def test_multiple_recognized_writers_stay_ambiguous():
    p = plan()
    p['writers'].append(copy.deepcopy(p['writers'][1]))
    result = pilot.trace_predicate(definition('json_report'), check(), p, ir(), {})
    assert result['path_relation'] == 'multiple_recognized_writers_same_path'
    assert 'literal_json_field_value' not in result


def test_declared_but_unwritten_artifact_and_unknown_id_are_distinct():
    source = ir()
    source['artifacts'].append({'artifact_id': 'unwritten'})
    a = pilot.trace_predicate(definition('unwritten'), check(), plan(), source, {})
    b = pilot.trace_predicate(definition('unknown'), check(), plan(), source, {})
    assert a['path_relation'] == 'declared_ir_artifact_not_in_recognized_outputs'
    assert b['path_relation'] == 'no_matching_recognized_writer'


def test_unknown_invocation_and_missing_script_reduce_coverage(tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'script.py').write_text(pilot.runtime_compiler._script_text(specs()))
    manifest = {'tasks': [{'intent_id': 'a', 'script': 'script.py', 'arguments': ['different']},
                          {'intent_id': 'b', 'script': 'missing.py'}]}
    result = pilot.scan_runtime(tmp_path, manifest, 100000)
    assert result['complete_recognized_writer_plan'] is False
    assert result['writers'] == []
    assert {r['state'] for r in result['scripts']} == {'unrecognized_task_invocation', 'missing_script'}


def test_recognized_script_is_parsed_not_imported_or_executed(tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'script.py').write_text(pilot.runtime_compiler._script_text(specs()))
    manifest = {'tasks': [{'intent_id': 'step', 'script': 'script.py',
                          'arguments': ['--workspace', '{workspace}', '--fixtures', '{fixtures}']}]}
    result = pilot.scan_runtime(tmp_path, manifest, 100000)
    assert result['complete_recognized_writer_plan'] is True
    assert len(result['writers']) == 3
    assert not (tmp_path / 'artifacts').exists()


@pytest.mark.parametrize('relative', ['../escape.py', '/tmp/escape.py', 'https://example.com/a.py'])
def test_script_paths_cannot_escape_or_fetch_network_content(relative, tmp_path):
    with pytest.raises(ValueError): pilot.local(tmp_path, relative)


def test_summary_counts_predicates_and_preserves_inspection_errors():
    records = [{'writer_plan': plan(), 'assertion_traces': [
        {'recorded_message_category': 'missing_or_empty_output_message', 'path_relation': 'same_artifact_id_different_suffix'}]},
        {'inspection_error': 'missing source'}]
    summary = pilot.summarize(records)
    assert summary['selected_cells'] == 2
    assert summary['inspection_errors'] == 1
    assert summary['missing_message_path_relations']['same_artifact_id_different_suffix'] == 1


def test_dry_run_never_materializes_or_scores(monkeypatch, capsys):
    monkeypatch.setattr(pilot, 'prepare', lambda: ({}, [{}], {}, {'x': 'sha'}))
    def forbidden(*args, **kwargs): raise AssertionError('No execution, materialization, or scoring')
    monkeypatch.setattr(pilot.runtime_compiler, 'materialize_runtime', forbidden)
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.subprocess, 'run', forbidden)
    assert pilot.main(['--dry-run']) == 0
    text = capsys.readouterr().out
    assert '"model_scripts_imported_or_executed": false' in text
    assert '"rescoring": false' in text
