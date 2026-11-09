"""Offline context signals stay separate from contract findings and scores."""
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_v2_candidate_contracts as audit


def document():
    return {'artifacts': [
        {'artifact_id': 'bundle', 'producer': ['a', 'b']},
        {'artifact_id': 'input', 'producer': None, 'fixture_ref': 'fixtures/inputs/data.csv'}],
        'bindings': [
            {'intent_id': 'a', 'input_bindings': [{'artifact_id': 'input'}], 'output_bindings': [{'artifact_id': 'bundle'}]},
            {'intent_id': 'b', 'input_bindings': [], 'output_bindings': [{'artifact_id': 'bundle'}]},
            {'intent_id': 'c', 'input_bindings': [{'artifact_id': 'bundle'}], 'output_bindings': [{'artifact_id': 'bundle'}]}]}


def result(findings):
    return {'findings': findings, 'finding_counts': dict(audit.Counter(f['category'] for f in findings))}


def test_context_inventories_links_writers_and_read_write_reuse_without_mutation():
    doc = document()
    original = copy.deepcopy(doc)
    row = audit.context_review(doc, ['fixtures/inputs/data.csv', 'task.md'])
    assert doc == original
    assert row['bound_external_inputs'] == [{'intent_id': 'a', 'artifact_id': 'input'}]
    assert row['artifact_fixture_links'] == [{'artifact_id': 'input', 'fixture_ref': 'fixtures/inputs/data.csv'}]
    assert row['multiple_writer_artifacts'] == {'bundle': ['a', 'b', 'c']}
    assert row['read_write_reuse'] == [{'intent_id': 'c', 'artifact_ids': ['bundle']}]
    assert not row['review_cues']
    assert 'dependency_cycle' not in str(row)


def test_absent_links_are_review_cues_not_automatic_semantic_failures():
    doc = document()
    doc['artifacts'].pop()
    doc['bindings'][0]['input_bindings'] = []
    row = audit.context_review(doc, ['fixtures/scenarios/nominal/data.csv'])
    assert len(row['review_cues']) == 2
    assert 'semantic_outcome' not in row
    assert 'catalog_contract' not in row


def test_no_fixture_files_does_not_invent_missing_file_findings():
    doc = {'artifacts': [], 'bindings': []}
    assert not audit.context_review(doc, ['task.md'])['review_cues']


def test_only_referenced_external_artifacts_count_as_bound():
    doc = document()
    doc['bindings'][0]['input_bindings'] = []
    row = audit.context_review(doc, ['fixtures/inputs/data.csv'])
    assert len(row['artifact_fixture_links']) == 1
    assert not row['bound_external_inputs']


def test_schema_repair_does_not_hide_persistent_contract_findings():
    schema = {'category': 'saved_structure', 'code': 'ir_schema_violation', 'subject': '/topology'}
    contract = {'category': 'catalog_contract', 'code': 'required_port_unbound', 'subject': 'output/report'}
    writer = {'category': 'dataflow', 'code': 'writer_producer_mismatch', 'subject': 'bundle'}
    context = audit.context_review(document(), [])
    row = audit.summarize(result([schema, contract, writer]), result([contract, writer]), context, context)
    assert row['before']['schema_violations'] == 1
    assert row['after']['schema_violations'] == 0
    assert row['before']['non_schema_hard_findings'] == row['after']['non_schema_hard_findings'] == 2
    assert row['non_schema_diagnostics_unchanged'] is True
    assert row['execution_status'] == 'blocked_by_static_contract_or_dataflow_findings'
    assert row['execution_ready'] is False
    assert row['semantic_outcome'] == 'not_measured'


def test_no_static_defect_still_does_not_prove_semantic_success():
    row = audit.summarize(result([]), result([]), {}, {})
    assert row['execution_status'] == 'requires_runtime_and_input_review'
    assert row['execution_ready'] is False
    assert row['semantic_outcome'] == 'not_measured'


def test_type_and_context_signals_are_not_silently_promoted_to_hard_defects():
    findings = [
        {'category': 'frozen_type_rule', 'code': 'port_data_type_not_exact', 'subject': 'report'},
        {'category': 'runtime_semantics', 'code': 'profile_parameter_without_enum', 'subject': 'operation'},
        {'category': 'input_context', 'code': 'external_input_link_unspecified', 'subject': 'input'}]
    assert audit.non_schema_hard(findings) == []
    row = audit.summarize(result(findings), result(findings), {}, {})
    assert len(row['after']['finding_counts']) == 3


def test_changed_diagnostics_and_input_context_are_visible():
    finding = {'category': 'catalog_contract', 'code': 'required_port_unbound', 'subject': 'report'}
    row = audit.summarize(result([finding]), result([]), {'links': []}, {'links': ['new']})
    assert row['non_schema_diagnostics_unchanged'] is False
    assert row['input_and_writer_context_unchanged'] is False


def test_dry_run_has_no_transport_or_execution(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError('No transport, workflow execution, or tests should run in dry-run')
    previous = {'case': 'main/unit', 'model_id': 'unit'}
    monkeypatch.setattr(audit, 'prepare', lambda: ({}, previous, {}, {}, [{}], {}, None, {}, {}, {'input': 'hash'}))
    monkeypatch.setattr(audit.generation.transport, 'complete', forbidden)
    monkeypatch.setattr(audit.subprocess, 'run', forbidden)
    assert audit.main(['--dry-run']) == 0
    text = capsys.readouterr().out
    assert '"api_requests": 0' in text
    assert '"workflow_executions": 0' in text
