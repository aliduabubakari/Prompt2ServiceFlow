"""Recorded attribution uses publication evidence without executing or rescoring."""
import copy
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_failure_attribution as pilot


def row():
    return {'model': 'unit', 'condition': 'primary', 'method': 'm4', 'split': 'main', 'instance': 'case',
            'sample_index': '0', 'semantic_success': '0', 'executable_valid': '1', 'run_validity': 'valid',
            'semantic_source': 'posthoc_scorer_1.2.1'}


def report(checks=None, **extra):
    return {'overall_status': 'fail', 'assertions_total': len(checks or []),
            'scenarios': [{'scenario': 'nominal', 'execution_status': 'pass', 'execution_errors': [],
                           'assertions': checks or []}], **extra}


def failure(message, status='fail'):
    return {'assertion_id': 'a', 'status': status, 'message': message}


@pytest.mark.parametrize('message,expected', [
    ('missing /tmp/artifacts/a.json', 'missing_or_empty_output_message'),
    ('value=1, expected=30', 'value_or_count_mismatch_message'),
    ('rows=2, minimum=4', 'value_or_count_mismatch_message'),
    ('length=0, expected=3', 'value_or_count_mismatch_message'),
    ('assertion evaluation error: KeyError', 'assertion_evaluation_error_message'),
    ('scenario execution failed', 'execution_error_propagated'),
    ('unexpected file /tmp/a.json', 'unexpected_output_message'),
    ("unsupported assertion type 'new'", 'unsupported_assertion_type_message'),
    ('unrecognized outcome', 'other_recorded_nonpass')])
def test_message_categories_are_literal_evidence_not_causal_labels(message, expected):
    assert pilot.message_category(failure(message)) == expected


def test_pass_is_not_reclassified_by_its_message():
    assert pilot.message_category(failure('value=30, expected=30', 'pass')) == 'recorded_pass'


def test_no_ir_precedes_gate_or_assertion_failures_in_exclusive_accounting():
    r = row()
    r['executable_valid'] = '0'
    observation = pilot.report_observations(report([failure('missing /tmp/a')]))
    assert pilot.classify(r, False, observation) == 'no_saved_ir'
    assert pilot.classify(r, True, observation) == 'recorded_public_gate_failure'


def test_published_pass_is_preserved_not_recomputed_from_messages():
    r = row()
    r['semantic_success'] = '1'
    assert pilot.classify(r, False, pilot.report_observations(None)) == 'published_end_to_end_pass'


def test_execution_and_alignment_failures_are_separate():
    execution = report([])
    execution['scenarios'][0]['execution_errors'] = ['Process exited 1']
    assert pilot.classify(row(), True, pilot.report_observations(execution)) == 'recorded_assertion_execution_failure'
    alias = report([], unmatched_assertion_scenarios=['run'])
    assert pilot.classify(row(), True, pilot.report_observations(alias)) == 'recorded_assertion_scenario_alignment_failure'


def test_empty_assertion_pass_is_not_semantic_success():
    raw = report([], overall_status='pass')
    assert pilot.classify(row(), True, pilot.report_observations(raw)) == 'empty_or_nonvacuity_unverifiable_assertion_record'


def test_missing_evidence_and_recorded_nonpasses_are_distinct():
    assert pilot.classify(row(), True, pilot.report_observations(None)) == 'assertion_record_unavailable_or_unscored'
    assert pilot.classify(row(), True, pilot.report_observations(report([failure('missing /tmp/a')])) ) == 'recorded_assertion_nonpass'


def test_main_uses_corrected_publication_record_not_old_vacuous_score():
    key = 'unit/primary/m4/main/case/0'
    corrected = report([failure('missing /tmp/a')])
    posthoc = {'results': {key: {'status': 'rescored', 'semantic_success': False, 'g6_assert': corrected}}}
    old = {'g6_assert': report([], overall_status='pass')}
    selected, source, _ = pilot.select_record(row(), {}, old, posthoc)
    assert selected == corrected
    assert source == 'published_main_posthoc'


def test_corrected_main_ledger_disagreement_is_not_hidden():
    posthoc = {'results': {'unit/primary/m4/main/case/0': {'semantic_success': True}}}
    with pytest.raises(ValueError): pilot.select_record(row(), {}, {}, posthoc)


def test_nonmain_missing_fullpass_flag_matches_original_denominator_rule():
    r = row()
    r.update(split='extension', semantic_source='frozen_manifest_nonvacuous_assertions')
    selected, _, _ = pilot.select_record(r, {'evaluation': {}}, None, {})
    assert selected is None
    r['semantic_success'] = '1'
    with pytest.raises(ValueError): pilot.select_record(r, {'evaluation': {}}, None, {})


def test_malformed_or_missing_manifest_cannot_silently_support_nonmain_reconciliation():
    r = row()
    r.update(split='extension', semantic_source='frozen_manifest_nonvacuous_assertions')
    with pytest.raises(ValueError): pilot.select_record(r, None, None, {})


def test_group_counts_keep_unknowns_and_overlapping_messages():
    records = [
        {'model': 'unit', 'method': 'm4', 'published_semantic_success': False,
         'recorded_stage_category': 'recorded_assertion_nonpass',
         'assertion_observations': {'assertion_message_counts': {'missing_or_empty_output_message': 6,
                                                               'value_or_count_mismatch_message': 1}}},
        {'model': 'unit', 'method': 'm4', 'published_semantic_success': False,
         'recorded_stage_category': 'inspection_error'}]
    result = pilot.aggregate(records)
    assert result['declared_cells'] == 2
    assert result['inspection_errors'] == 1
    group = result['groups'][0]
    assert group['declared_cells'] == 2
    assert group['cells_with_nonpass_message_category']['missing_or_empty_output_message'] == 1
    assert group['assertion_message_counts']['missing_or_empty_output_message'] == 6


def test_classification_does_not_change_source_report():
    raw = report([failure('value=1, expected=30')])
    original = copy.deepcopy(raw)
    assert pilot.classify(row(), True, pilot.report_observations(raw)) == 'recorded_assertion_nonpass'
    assert raw == original


@pytest.mark.parametrize('value', ['False', 'unknown', 2, float('nan')])
def test_unknown_flags_are_not_coerced_to_pass(value):
    with pytest.raises(ValueError): pilot.flag(value)


def test_dry_run_has_no_scorer_or_execution_call(monkeypatch, capsys):
    r = row()
    monkeypatch.setattr(pilot, 'prepare', lambda: ({'methods': ['m4']}, [r], {}, {}, {}, {'x': 'sha'}))
    def forbidden(*args, **kwargs): raise AssertionError('No execution, inference, or rescoring')
    monkeypatch.setattr(pilot.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(pilot.controls, '_execute_scenarios', forbidden)
    monkeypatch.setattr(pilot.controls, '_evaluate_assertion', forbidden)
    monkeypatch.setattr(pilot.subprocess, 'run', forbidden)
    assert pilot.main(['--dry-run']) == 0
    assert '"rescoring": false' in capsys.readouterr().out
