"""Synthetic saved documents only; never execute the original model outputs."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'audit/v2'), str(ROOT / 'audit')]
import replay_v2_csv_saved_ir as runner

analysis, adapter = runner.analysis, runner.adapter
factory = runner.previous.factory
RAW = b'key,quantity\na,10\nb,20\n'


def synthetic(tmp_path, service=adapter.SNAPSHOT):
    """An authored test document; its toy full schema is not the benchmark schema."""
    workspace = tmp_path / 'public'; nominal = workspace / 'fixtures/scenarios/nominal'; nominal.mkdir(parents=True)
    ir, _ = factory.authored(RAW, service, tmp_path / 'unused_authored_fixture')
    (nominal / 'batch_17.csv').write_bytes(RAW)
    (nominal / 'location.json').write_text(json.dumps({'driver': 'filesystem-mock', 'path': '/audit/landing', 'filename_pattern': 'batch_*.csv'}))
    (nominal / 'target.json').write_text(json.dumps({'driver': 'filesystem-mock', 'engine': 'postgresql', 'target': 'workspace/mock_postgres'}))
    refs = {'origin': 'fixtures/inputs/batch_17.csv', 'location': 'fixtures/inputs/location.json', 'destination': 'fixtures/inputs/target.json'}
    fields = {'availability_decision': {'available': 'boolean'}, 'check_status': {'success': 'boolean'},
        'validated_dataset': {'columns': 'array', 'rows': 'array'}, 'validated_data_object': {'source_uri': 'string', 'record_count': 'integer', 'columns': 'array'},
        'validation_status': {'success': 'boolean', 'rows_read': 'integer'},
        'target_database_reference': {'target_table': 'string', 'rows_imported': 'integer'}, 'load_status': {'success': 'boolean', 'rows_loaded': 'integer'}}
    for a in ir['artifacts']:
        if a['artifact_id'] in refs: a['fixture_ref'] = refs[a['artifact_id']]
    for port, spec in fields.items():
        path = workspace / 'contracts/artifacts' / factory.SCHEMA_NAMES[port]; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'type': 'object', 'required': list(spec), 'properties': {k: {'type': v} for k, v in spec.items()}}))
    source_path = tmp_path / 'saved_ir.yaml'; source_path.write_text(json.dumps(ir))
    source = {'id': 'synthetic-model/m5/synthetic/input/0', 'artifact': str(source_path), 'model': 'synthetic-model', 'method': 'm5',
              'case': 'synthetic/input', 'sample_index': 0, 'route': 'serviceflow_ir', 'original_method_status': 'completed'}
    context = {'workspace': str(workspace), 'source_csv': 'fixtures/scenarios/nominal/batch_17.csv',
        'schema': {'type': 'object', 'required': ['bindings', 'service_intents', 'artifacts', 'control_flow', 'runtime']}}
    design = json.loads(runner.CONFIG.read_text())
    return source, ir, context, design


def save(source, ir): Path(source['artifact']).write_text(json.dumps(ir))


@pytest.mark.parametrize('service', [adapter.SNAPSHOT, adapter.TABULAR])
def test_explicit_resources_preserve_source_graph_parameters_and_schemas(tmp_path, service):
    source, ir, context, design = synthetic(tmp_path, service); original = Path(source['artifact']).read_bytes()
    row = analysis.inspect(source, context, design)
    assert row['state'] == 'admitted' and row['full_ir_schema_valid'] is True
    assert row['plan']['source_ir'] == ir and Path(source['artifact']).read_bytes() == original
    assert row['target']['schema'] == 'p2sf_adapter' and row['target']['logical_name'] == 'p2sf_adapter.records_generic'
    assert row['plan']['schemas']['contracts/artifacts/load_status.schema.json']['required'] == ['success', 'rows_loaded']
    assert row['plan']['intervention']['fixtures']['fixtures/inputs/target.json']['resource']['schema'] == 'public'


def test_full_ir_validation_precedes_adapter_admission(tmp_path):
    source, ir, context, design = synthetic(tmp_path)
    context['schema']['required'].append('missing_source_metadata')
    row = analysis.inspect(source, context, design)
    assert row['state'] == 'blocked' and row['findings'][0]['code'] == 'full_ir_schema_error' and 'plan' not in row


@pytest.mark.parametrize('defect,code', [
    ('no_binding', 'missing_fixture_link'), ('absent_fixture', 'explicit_fixture_missing'),
    ('no_columns', 'missing_required_columns'), ('wrong_columns', 'required_columns_absent_from_public_csv'),
    ('columns_mapping', 'nonidentity_columns'), ('upsert', 'unsupported_write_mode'),
    ('missing_output_schema', 'original_output_schema_unavailable'), ('external_schema', 'nonlocal_schema'),
    ('wrong_resource', 'unsupported_source_resource'), ('no_logical_root', 'unmapped_filesystem_resource'),
    ('unresolved_date', 'unresolved_parameters'), ('no_gate', 'unsupported_gate'), ('wrong_edges', 'unsupported_dependency')])
def test_choices_are_blocked_without_repairs_or_schema_substitution(tmp_path, defect, code):
    source, ir, context, design = synthetic(tmp_path)
    if defect == 'no_binding': ir['artifacts'][0].pop('fixture_ref')
    elif defect == 'absent_fixture': ir['artifacts'][0]['fixture_ref'] = 'fixtures/inputs/not_provided.csv'
    elif defect == 'no_columns': runner.previous.parameters(ir, adapter.CSV).pop('required_columns')
    elif defect == 'wrong_columns': runner.previous.parameters(ir, adapter.CSV)['required_columns'] = ['sales_amount']
    elif defect == 'columns_mapping': runner.previous.parameters(ir, adapter.SNAPSHOT)['import_spec']['columns'].reverse()
    elif defect == 'upsert': runner.previous.parameters(ir, adapter.SNAPSHOT)['load_mode'] = 'upsert'
    elif defect == 'missing_output_schema': (Path(context['workspace']) / 'contracts/artifacts/load_status.schema.json').unlink()
    elif defect == 'external_schema':
        (Path(context['workspace']) / 'contracts/artifacts/load_status.schema.json').write_text(json.dumps({'$ref': 'https://example.invalid/schema'}))
    elif defect == 'wrong_resource':
        (Path(context['workspace']) / 'fixtures/scenarios/nominal/target.json').write_text(json.dumps({'driver': 'production', 'engine': 'postgresql'}))
    elif defect == 'no_logical_root':
        (Path(context['workspace']) / 'fixtures/scenarios/nominal/location.json').write_text(json.dumps({'driver': 'filesystem-mock'}))
    elif defect == 'unresolved_date': runner.previous.parameters(ir, adapter.SENSOR)['path'] = '/audit/{{ ds }}'
    elif defect == 'no_gate': ir['control_flow']['gates'] = []
    elif defect == 'wrong_edges': ir['control_flow']['edges'].pop()
    save(source, ir); original = Path(source['artifact']).read_bytes()
    row = analysis.inspect(source, context, design)
    assert row['state'] == 'blocked' and row['findings'][0]['code'] == code, row
    assert Path(source['artifact']).read_bytes() == original


@pytest.mark.parametrize('kind', ['missing', 'parse', 'alias', 'multiple'])
def test_missing_and_unreadable_documents_stay_in_coverage(tmp_path, kind):
    source, ir, context, design = synthetic(tmp_path); p = Path(source['artifact'])
    if kind == 'missing': p.unlink()
    elif kind == 'parse': p.write_text('!python/unsafe {}')
    elif kind == 'alias': p.write_text('one: &first {}\ntwo: *first\n')
    else: p.write_text('{}\n---\n{}\n')
    row = analysis.inspect(source, context, design)
    assert row['source'] == source and row['state'] != 'admitted' and row['semantic_outcome'] == 'not_measured'


@pytest.mark.parametrize('scenario', ['nominal', 'changed_value', 'extra_row', 'missing_file', 'missing_required_column'])
def test_probe_materialization_changes_only_declared_copied_bytes(tmp_path, scenario):
    source, ir, context, design = synthetic(tmp_path); row = analysis.inspect(source, context, design)
    plan, raw = analysis.materialize(row, tmp_path / 'trial', scenario)
    assert plan['source_ir'] == ir and plan['schemas'] == row['plan']['schemas']
    assert plan['source_ir_sha256'] == row['plan']['source_ir_sha256']
    assert (Path(context['workspace']) / context['source_csv']).read_bytes() == RAW
    for ref, entry in plan['intervention']['fixtures'].items():
        path = tmp_path / 'trial' / entry['path']
        if entry['kind'] != 'csv': assert path.read_bytes() == Path(row['fixture_sources'][ref]).read_bytes()
        elif raw is None: assert not path.exists() and entry['sha256'] == 'MISSING'
        else: assert path.read_bytes() == raw and entry['sha256'] == analysis.sha(raw)


def test_checkpoint_checks_all_evidence_not_just_result_flag(tmp_path):
    source, ir, context, design = synthetic(tmp_path); row = analysis.inspect(source, context, design)
    directory = tmp_path / 'checkpoint'; directory.mkdir(); (directory / 'data.json').write_text('{}')
    saved = runner.checkpoint(directory, row, {'state': 'synthetic'})
    assert runner.verify_checkpoint(saved, row)['state'] == 'synthetic'
    (directory / 'data.json').write_text('{"changed":true}')
    with pytest.raises(ValueError, match='evidence changed'): runner.verify_checkpoint(saved, row)


def test_frozen_implementation_lock_requires_exact_files_and_bytes(tmp_path):
    (tmp_path / 'one.py').write_text('# authored test\n')
    files = {'one.py': runner.controls.sha256(tmp_path / 'one.py')}
    runner.verify_named_inputs(tmp_path, files, ['one.py'])
    with pytest.raises(ValueError, match='roster differs'): runner.verify_named_inputs(tmp_path, files, ['one.py', 'other.py'])
    (tmp_path / 'one.py').write_text('# changed\n')
    with pytest.raises(ValueError, match='implementation changed'): runner.verify_named_inputs(tmp_path, files, ['one.py'])


def test_business_oracle_cannot_accept_a_success_flag_or_missing_schema(tmp_path):
    snapshot = {'exists': False, 'columns': [], 'types': [], 'rows': []}
    receipt = {'state': 'loaded', 'load_status': {'success': True, 'rows_written': 2, 'rows_loaded': 2}}
    assert analysis.evaluate('nominal', RAW, receipt, None, snapshot, snapshot)['pass'] is False
    receipt['load_status']['rows_loaded'] = 0
    real = {'exists': True, 'columns': ['key', 'quantity'], 'types': ['text', 'text'], 'rows': [['a', '10'], ['b', '20']]}
    assert analysis.evaluate('nominal', RAW, receipt, None, snapshot, real)['pass'] is False


@pytest.mark.parametrize('code,expected', [('23514', False), ('42601', False), ('08006', True), ('53300', True), ('57P01', True), ('XX000', True), (None, True)])
def test_environment_failures_are_pending_infrastructure_not_business_results(code, expected):
    error = runner.transport.DatabaseError('connection lost' if code is None else 'ERROR: ' + code + ': test error')
    assert runner.database_infrastructure_failure(error) is expected


@pytest.mark.parametrize('defect', ['none', 'design', 'manifest', 'plan', 'unknown_cell'])
def test_resume_requires_exact_plan_inputs_design_and_roster(tmp_path, defect):
    source, ir, context, design = synthetic(tmp_path)
    row = analysis.inspect(source, context, design)
    prepared = {'rows': [row], 'design': design, 'direct_argo_backlog': [], 'hashes': {'one': 'a'}}
    output = tmp_path / 'output'; output.mkdir()
    frozen = {'rows': [row], 'direct_argo_backlog': []}
    run = {'input_fingerprint': runner.controls.fingerprint(prepared['hashes']), 'frozen_plan_sha256': adapter.digest(frozen),
           'design': copy.deepcopy(design), 'image': {'id': 'fixed'}, 'completed_cells': {}}
    runner.controls.write_json(output / 'frozen_plan.json', frozen)
    runner.controls.write_json(output / 'input_sha256.json', prepared['hashes'])
    if defect == 'design': run['design']['database_default_schema'] = 'different'
    elif defect == 'manifest': runner.controls.write_json(output / 'input_sha256.json', {})
    elif defect == 'plan': runner.controls.write_json(output / 'frozen_plan.json', {})
    elif defect == 'unknown_cell': run['completed_cells']['foreign'] = {}
    if defect == 'none': runner.validate_resume(output, run, prepared, {'id': 'fixed'})
    else:
        with pytest.raises(ValueError): runner.validate_resume(output, run, prepared, {'id': 'fixed'})


@pytest.mark.parametrize('gate_bug', [False, True])
def test_actual_postgres_synthetic_saved_ir_five_probes_and_failed_gate(tmp_path, gate_bug):
    image_name = os.environ.get('P2SF_POSTGRES_TEST_IMAGE')
    if not image_name: pytest.skip('Set P2SF_POSTGRES_TEST_IMAGE for actual PostgreSQL synthetic replay')
    source, ir, context, design = synthetic(tmp_path)
    if gate_bug:
        sensor = runner.previous.parameters(ir, adapter.SENSOR)
        sensor['availability_condition'] = 'exists'; sensor.pop('filename_pattern')
        save(source, ir)
    row = analysis.inspect(source, context, design); assert row['state'] == 'admitted'
    saved = runner.run_cell(row, tmp_path / 'replay', runner.transport.image_info(image_name), design)
    result = runner.verify_checkpoint(saved, row)
    assert result['state'] == 'replayed' and result['nominal_business_pass'] is True
    assert result['business_suite_pass'] is (not gate_bug)
    assert len(result['trials']) == 5
    if gate_bug:
        failed = [t for t in result['trials'] if not t['pass']]
        assert [t['scenario'] for t in failed] == ['missing_file']
    assert Path(source['artifact']).read_bytes() == (tmp_path / 'replay/original_saved_ir.yaml').read_bytes()
